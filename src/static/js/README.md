# HTMX SSE Extension Fix

## Problem Description

The original HTMX SSE (Server-Sent Events) extension has a race condition in its reconnection logic that can cause browser freezing, particularly after system suspend/resume cycles. When a laptop goes to sleep and wakes up, the EventSource connection drops, triggering multiple rapid error events that attempt to reconnect simultaneously.

This creates a "thundering herd" problem where:
- Multiple EventSource objects are created concurrently  
- Event listeners are attached simultaneously to the same elements
- Internal data structures are accessed/modified by multiple reconnection attempts
- Browser resources become overwhelmed, leading to tab freezing or browser lockup

This issue is documented in Mozilla Bug #1251117 and affects EventSource reliability across different browsers.

## The Fix

The fix adds a `sseReconnecting` flag to prevent multiple simultaneous reconnection attempts. Only one reconnection can proceed at a time, with others being safely ignored.

## Code Changes

Here's the diff of changes made to the `ensureEventSource` function's `onerror` handler:

```diff
  source.onerror = function(err) {
    // Log an error event
    api.triggerErrorEvent(elt, 'htmx:sseError', { error: err, source })

    // If parent no longer exists in the document, then clean up this EventSource
    if (maybeCloseSSESource(elt)) {
      return
    }

+   // Prevent multiple simultaneous reconnection attempts
+   var internalData = api.getInternalData(elt)
+   if (internalData.sseReconnecting) {
+     return
+   }

    // Otherwise, try to reconnect the EventSource
    if (source.readyState === EventSource.CLOSED) {
-     retryCount = retryCount || 0
-     retryCount = Math.max(Math.min(retryCount * 2, 128), 1)
-     var timeout = retryCount * 500
-     window.setTimeout(function() {
-       ensureEventSourceOnElement(elt, retryCount)
-     }, timeout)
+     internalData.sseReconnecting = true
+     var nextRetryCount = retryCount || 0
+     nextRetryCount = Math.max(Math.min(nextRetryCount * 2, 128), 1)
+     var timeout = nextRetryCount * 500
+
+     window.setTimeout(function() {
+       internalData.sseReconnecting = false
+       ensureEventSourceOnElement(elt, nextRetryCount)
+     }, timeout)
    }
  }
```

## How It Works

1. **Race Condition Prevention**: Before attempting reconnection, check if `internalData.sseReconnecting` is already true
2. **Flag Management**: Set `sseReconnecting = true` before starting reconnection attempt
3. **Sequential Processing**: If another error occurs while reconnecting, it's safely ignored
4. **Flag Cleanup**: Clear `sseReconnecting = false` after the reconnection completes
5. **Preserved Logic**: All existing exponential backoff and retry logic remains intact

## Testing the Fix

### Browser DevTools Method (Most Reliable)
1. Open browser DevTools → Network tab
2. Set network throttling to "Offline" 
3. Wait 2-3 seconds for SSE errors in console
4. Set back to "Online"
5. Repeat rapidly 3-4 times to simulate multiple connection drops

### System Suspend/Resume Method
1. Open Octovox Switchboard in browser tab
2. Close laptop lid (suspend system)
3. Wait 10+ seconds
4. Open lid (resume system)
5. Check if tab responds normally vs. freezing

### Network Drop Simulation
```bash
# Block SSE connection (adjust port as needed)
sudo iptables -A OUTPUT -p tcp --dport 5000 -j DROP
# Wait 10 seconds, then restore
sudo iptables -D OUTPUT -p tcp --dport 5000 -j DROP
```

## Expected Behavior

**Before Fix (Problematic):**
```
htmx:sseError (multiple rapid entries)
EventSource connection attempts... (many simultaneous)
[Browser may freeze or become unresponsive]
```

**After Fix (Correct):**
```
htmx:sseError
[pause for exponential backoff delay]
htmx:sseOpen (single successful reconnection)
```

## Files Modified

- `sse.min.js` - Minified version with the fix applied (active)
- `sse.min.js.backup` - Original unmodified version (backup)

## Build Process

The fix was applied using the same tools as the HTMX project:

```bash
# Install minification tool
npm install uglify-js --save-dev

# Apply fix to source code
# (manual edit of onerror handler)

# Minify with same settings as HTMX project  
npx uglifyjs sse-fixed.js -o sse-fixed.min.js -c -m
```

## Upstream Contribution

This fix addresses a legitimate race condition in the HTMX SSE extension. Consider contributing it back to the HTMX project:

- **Repository**: https://github.com/bigskysoftware/htmx-extensions
- **File**: `src/sse/sse.js` 
- **Issue**: Race condition in EventSource reconnection after system suspend/resume

The fix is minimal, preserves all existing functionality, and significantly improves stability for long-running SSE connections.

## Related Issues

- Mozilla Bug #1251117: EventSource doesn't retry after OS suspend/resume
- HTMX GitHub discussions about SSE reconnection reliability
- Browser-specific EventSource behavior differences during sleep/wake cycles