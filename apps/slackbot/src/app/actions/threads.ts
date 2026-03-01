"use server";

const API_URL = process.env.AI_V2_API_URL || "http://api:8000";
const API_KEY = process.env.AI_V2_API_KEY || "";

type ReplyAttachment = { url: string; name: string };

export async function postReply(threadKey: string, reply: string, attachments?: ReplyAttachment[]) {
  const res = await fetch(`${API_URL}/slack/reply`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      thread_key: threadKey,
      reply,
      ...(attachments && attachments.length > 0 ? { attachments } : {}),
      source: "thread_ui",
    }),
  });
  if (!res.ok) {
    throw new Error(`Reply failed: ${res.status}`);
  }
  const data = await res.json();
  if (data.status === "ignored_empty") {
    throw new Error("Reply is empty.");
  }
  if (data.status === "no_active_session") {
    throw new Error("No active engineer session for this thread.");
  }
  if (data.status === "not_waiting_for_reply") {
    throw new Error("Engineer is not currently waiting for a reply.");
  }
  return data;
}
