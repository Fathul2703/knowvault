/** A Server-Sent Events message: the event name and its data lines joined. */
export type SseMessage = { event: string; data: string };

function parseBlock(block: string): SseMessage | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) {
      continue; // comment or keep-alive
    }
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }
    if (field === "event") {
      event = value;
    } else if (field === "data") {
      data.push(value);
    }
  }
  return data.length ? { event, data: data.join("\n") } : null;
}

/**
 * Incremental parser for a `text/event-stream` body. Network chunks can end anywhere, so text
 * is buffered until a blank line completes a message.
 */
export class SseParser {
  private buffer = "";

  push(chunk: string): SseMessage[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const messages: SseMessage[] = [];
    let end = this.buffer.indexOf("\n\n");
    while (end !== -1) {
      const message = parseBlock(this.buffer.slice(0, end));
      if (message) {
        messages.push(message);
      }
      this.buffer = this.buffer.slice(end + 2);
      end = this.buffer.indexOf("\n\n");
    }
    return messages;
  }

  /** Returns a final message that was not followed by a blank line. */
  flush(): SseMessage[] {
    const rest = this.buffer;
    this.buffer = "";
    const message = rest.trim() ? parseBlock(rest) : null;
    return message ? [message] : [];
  }
}
