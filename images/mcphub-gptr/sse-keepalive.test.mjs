// Build-time smoke test for sse-keepalive.js. Runs inside the image build
// (then the file is removed), and locally via `node sse-keepalive.test.mjs`.
// Covers: keepalive comments on an idle SSE stream (the exact failure that
// orphaned gpt-researcher write_report results behind Open WebUI's 300 s
// read timeout), no comments on non-SSE responses, and no stray writes after
// a response has ended.

import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';

process.env.MCPHUB_SSE_KEEPALIVE_MS = '50';

const { sseKeepaliveMiddleware } = await import('./home-server-sse-keepalive.js');

const watchdog = setTimeout(() => {
    console.error('sse-keepalive.test: watchdog fired, test hung');
    process.exit(1);
}, 10000);

const heldResponses = [];

const server = http.createServer((req, res) => {
    sseKeepaliveMiddleware(req, res, () => {
        if (req.url === '/idle-sse') {
            // Headers explicitly passed to writeHead, the shape hono's
            // node-server adapter uses. Nothing is ever written after the
            // first event: this is the long-tool-call case.
            res.writeHead(200, {
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache, no-transform',
                Connection: 'keep-alive',
            });
            res.write('event: message\ndata: started\n\n');
            heldResponses.push(res);
            return;
        }
        if (req.url === '/implicit-sse') {
            // Headers set via setHeader with an implicit writeHead path.
            res.setHeader('Content-Type', 'text/event-stream');
            res.write('event: message\ndata: started\n\n');
            heldResponses.push(res);
            return;
        }
        // Ordinary JSON response must never receive keepalive comments.
        res.setHeader('Content-Type', 'application/json');
        res.end('{"ok":true}');
    });
});

server.listen(0, '127.0.0.1');
await once(server, 'listening');
const port = server.address().port;

async function collect(path, durationMs) {
    const request = http.get({ port, path, agent: false });
    const chunks = [];
    request.on('response', (response) => {
        response.on('data', (chunk) => chunks.push(chunk.toString()));
    });
    await new Promise((resolve) => setTimeout(resolve, durationMs));
    request.destroy();
    return chunks.join('');
}

// Idle SSE: first event immediately, then silence — keepalive must arrive.
const idleBody = await collect('/idle-sse', 400);
assert.match(idleBody, /event: message\ndata: started/, 'initial SSE event missing');
assert.match(idleBody, /: keepalive/, 'no keepalive comment on idle SSE stream');

// Implicit-header SSE path must be detected too.
const implicitBody = await collect('/implicit-sse', 400);
assert.match(implicitBody, /: keepalive/, 'no keepalive comment on implicit-header SSE');

// JSON response: exact body, no comments.
const jsonResponse = await new Promise((resolve, reject) => {
    http.get({ port, path: '/', agent: false }, (response) => {
        const chunks = [];
        response.on('data', (chunk) => chunks.push(chunk.toString()));
        response.on('end', () => resolve(chunks.join('')));
    }).on('error', reject);
});
assert.equal(jsonResponse, '{"ok":true}');
assert.doesNotMatch(jsonResponse, /keepalive/, 'keepalive leaked into a JSON response');

// After end/close the timer must be cleared: wait several intervals and
// assert no write-after-end occurred (the wrappers surface it as an error).
await new Promise((resolve) => setTimeout(resolve, 300));
for (const res of heldResponses) {
    assert.equal(res.writableEnded || res.destroyed, true, 'held SSE response not closed');
}

clearTimeout(watchdog);
server.close();
for (const res of heldResponses) {
    res.destroy();
}
console.log('sse-keepalive.test: ok');
process.exit(0);
