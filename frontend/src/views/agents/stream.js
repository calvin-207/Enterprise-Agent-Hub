/** Authenticated SSE reader with event cursor. Never place JWT in a URL. */
import { getToken } from "@/utils/util";
import sysConfig from "@/config";

export async function streamRunEvents(runId, after, onEvent, { signal } = {}) {
  const url = sysConfig.API_URL + "/api/platform/v1/runs/" + encodeURIComponent(runId) + "/stream/?after=" + after;
  const res = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: sysConfig.TOKEN_PREFIX + getToken(),
      Accept: "text/event-stream",
      "Last-Event-ID": String(after),
    },
    signal,
    cache: "no-store",
  });
  if (!res.ok || !res.body) throw new Error("事件流不可用：" + res.status);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      // SSE records are separated by a blank line.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";
      for (const frame of frames) {
        if (frame.startsWith(":")) continue;
        const fields = frame.split("\n");
        const kind = fields.find(line => line.startsWith("event:"))?.slice(6).trim();
        const id = Number(fields.find(line => line.startsWith("id:"))?.slice(3).trim());
        const raw = fields.filter(line => line.startsWith("data:")).map(line => line.slice(5).trim()).join("\n");
        if (kind === "stream-end") return "complete";
        if (kind === "run-event" && raw && Number.isSafeInteger(id) && id > after) {
          after = id;
          onEvent(JSON.parse(raw));
        }
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
  }
  return "reconnect";
}
