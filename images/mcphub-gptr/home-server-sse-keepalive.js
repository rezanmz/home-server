// home-server: keep MCP SSE response streams from going silently dead.
//
// Open WebUI's MCP client (Python mcp SDK) reads Streamable-HTTP SSE streams
// with a 300 s read timeout and no traffic of its own on an idle stream. A
// long-running tool call (gpt-researcher write_report takes ~5 minutes)
// produces no bytes until it finishes, so the client drops the POST stream
// before the result arrives; the pending callTool never resolves and the chat
// hangs with an empty message while the paid-for result is discarded. The
// sibling lesson "Library print() corrupts FastMCP stdio JSON-RPC" documents
// the earlier instance of the same "server finished, client hung" signature.
//
// Every Streamable-HTTP/SSE response through MCPHub's Express app passes
// writeHead here (directly or via Node's implicit header path). When the
// response is text/event-stream we start an idle timer that writes standard
// SSE comment lines (": keepalive\n\n"). SSE comments are ignored by every
// conforming parser but count as received bytes, so they reset read timeouts
// on every hop without touching the protocol stream.

const DEFAULT_INTERVAL_MS = 15000;

function intervalMs() {
    const raw = Number(process.env.MCPHUB_SSE_KEEPALIVE_MS);
    return Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_INTERVAL_MS;
}

function headerValue(res, writeHeadArgs, name) {
    const stored = res.getHeader(name);
    if (stored !== undefined) {
        return String(stored);
    }
    for (const arg of writeHeadArgs) {
        if (arg === null || typeof arg !== 'object') {
            continue;
        }
        if (Array.isArray(arg)) {
            for (const pair of arg) {
                if (Array.isArray(pair) && String(pair[0]).toLowerCase() === name) {
                    return String(pair[1]);
                }
            }
            continue;
        }
        for (const [key, value] of Object.entries(arg)) {
            if (key.toLowerCase() === name) {
                return String(value);
            }
        }
    }
    return '';
}

export function sseKeepaliveMiddleware(req, res, next) {
    let timer = null;
    let lastActivity = Date.now();
    const originalWriteHead = res.writeHead;
    const originalWrite = res.write;
    const originalEnd = res.end;

    const stop = () => {
        if (timer !== null) {
            clearInterval(timer);
            timer = null;
        }
    };

    res.write = function (...args) {
        lastActivity = Date.now();
        return originalWrite.apply(this, args);
    };
    res.end = function (...args) {
        lastActivity = Date.now();
        stop();
        return originalEnd.apply(this, args);
    };
    res.writeHead = function (...args) {
        const result = originalWriteHead.apply(this, args);
        if (timer === null && /text\/event-stream/i.test(headerValue(res, args, 'content-type'))) {
            timer = setInterval(() => {
                if (res.writableEnded || res.destroyed) {
                    stop();
                    return;
                }
                // Only speak when the stream would otherwise be silent for
                // another full interval; active streams need no comments.
                if (Date.now() - lastActivity < intervalMs()) {
                    return;
                }
                try {
                    originalWrite.call(res, ': keepalive\n\n');
                }
                catch {
                    stop();
                }
            }, intervalMs());
            res.on('close', stop);
            res.on('finish', stop);
        }
        return result;
    };
    next();
}
