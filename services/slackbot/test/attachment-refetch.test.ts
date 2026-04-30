import { describe, it, expect, vi } from "vitest";

/**
 * Simulates the attachment extraction logic from bot.ts onNewMention.
 *
 * Problem: Slack app_mention events don't always include `files`, so the
 * normalized message can have message.attachments = []. The fix re-fetches the message via
 * adapter.fetchMessage() which uses conversations.replies (includes files).
 */

// ── Simulate the Slack adapter's createAttachment mapping ──

function createAttachment(file: {
  url_private?: string;
  name?: string;
  mimetype?: string;
  size?: number;
}) {
  const url = file.url_private;
  let type: "image" | "file" | "video" | "audio" = "file";
  if (file.mimetype?.startsWith("image/")) type = "image";
  else if (file.mimetype?.startsWith("video/")) type = "video";
  else if (file.mimetype?.startsWith("audio/")) type = "audio";
  return { type, url, name: file.name, mimeType: file.mimetype, size: file.size };
}

// ── Simulate the parseSlackMessage attachment mapping ──

function parseEventAttachments(event: { files?: Array<Record<string, unknown>> }) {
  return (event.files || []).map((file) => createAttachment(file));
}

// ── The actual bot.ts logic for extracting attachments in onNewMention ──

function extractAttachmentsFromMention(
  messageAttachments: Array<{ url?: string; name?: string; mimeType?: string }> | undefined,
  refetchedAttachments: Array<{ url?: string; name?: string; mimeType?: string }> | null,
) {
  let attachments = messageAttachments?.map((a) => ({
    url: a.url,
    name: a.name,
    mimeType: a.mimeType,
  }));

  // Re-fetch fallback (mirrors bot.ts logic)
  if ((!attachments || attachments.length === 0) && refetchedAttachments) {
    if (refetchedAttachments.length > 0) {
      attachments = refetchedAttachments.map((a) => ({
        url: a.url,
        name: a.name,
        mimeType: a.mimeType,
      }));
    }
  }

  return attachments;
}

// ── Content block builder (mirrors bot.ts resolveAttachmentBlocks) ──

type ContentBlock =
  | { type: "text"; text: string }
  | { type: "image"; source: { type: "base64"; media_type: string; data: string } }
  | { type: "document"; source: { type: "base64"; media_type: string; data: string } };

async function resolveAttachmentBlocks(
  attachments: Array<{ mimeType?: string; fetchData?: () => Promise<Buffer> }>,
): Promise<ContentBlock[]> {
  const blocks: ContentBlock[] = [];
  for (const att of attachments) {
    if (!att.fetchData || !att.mimeType) continue;
    const data = await att.fetchData();
    const b64 = data.toString("base64");
    if (att.mimeType.startsWith("image/")) {
      blocks.push({ type: "image", source: { type: "base64", media_type: att.mimeType, data: b64 } });
    } else {
      blocks.push({ type: "document", source: { type: "base64", media_type: att.mimeType, data: b64 } });
    }
  }
  return blocks;
}

describe("Slack attachment re-fetch", () => {
  it("app_mention event has no files — attachments are empty", () => {
    // Slack app_mention payload — no `files` field
    const appMentionEvent = {
      type: "app_mention",
      user: "U061F7AUR",
      text: "<@U0LAN0Z89> read this pdf",
      ts: "1773355015.044909",
      channel: "C0AJ07U8Z1N",
      event_ts: "1773355015044909",
      // NOTE: no `files` field!
    };

    const attachments = parseEventAttachments(appMentionEvent as { files?: Array<Record<string, unknown>> });
    expect(attachments).toEqual([]);
  });

  it("conversations.replies response includes files", () => {
    // What conversations.replies returns for the same message
    const repliesMessage = {
      type: "message",
      user: "U061F7AUR",
      text: "<@U0LAN0Z89> read this pdf",
      ts: "1773355015.044909",
      files: [
        {
          id: "F0ALASAT36E",
          name: "March 9.5 2026.pdf",
          title: "March 9.5 2026.pdf",
          mimetype: "application/pdf",
          filetype: "pdf",
          url_private: "https://files.slack.com/files-pri/T04B5AGS7K7-F0ALASAT36E/march_9.5_2026.pdf",
          size: 1731523,
        },
      ],
    };

    const attachments = parseEventAttachments(repliesMessage);
    expect(attachments).toHaveLength(1);
    expect(attachments[0]).toEqual({
      type: "file",
      url: "https://files.slack.com/files-pri/T04B5AGS7K7-F0ALASAT36E/march_9.5_2026.pdf",
      name: "March 9.5 2026.pdf",
      mimeType: "application/pdf",
      size: 1731523,
    });
  });

  it("re-fetch fallback populates attachments when app_mention has none", () => {
    // Step 1: app_mention — no files
    const mentionAttachments = parseEventAttachments({ /* no files */ });
    expect(mentionAttachments).toEqual([]);

    // Step 2: re-fetched message via conversations.replies — has files
    const refetchedAttachments = parseEventAttachments({
      files: [
        {
          name: "report.pdf",
          mimetype: "application/pdf",
          url_private: "https://files.slack.com/files-pri/T-XXXXX/report.pdf",
          size: 500000,
        },
      ],
    });

    // Step 3: bot.ts logic combines them
    const result = extractAttachmentsFromMention(mentionAttachments, refetchedAttachments);
    expect(result).toHaveLength(1);
    expect(result![0].url).toBe("https://files.slack.com/files-pri/T-XXXXX/report.pdf");
    expect(result![0].name).toBe("report.pdf");
    expect(result![0].mimeType).toBe("application/pdf");
  });

  it("content blocks are built correctly for refetched PDF attachment", async () => {
    const pdfData = Buffer.from("fake-pdf-content");
    const blocks = await resolveAttachmentBlocks([
      {
        mimeType: "application/pdf",
        fetchData: async () => pdfData,
      },
    ]);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].type).toBe("document");
    expect((blocks[0] as any).source.media_type).toBe("application/pdf");
    expect((blocks[0] as any).source.data).toBe(pdfData.toString("base64"));
  });

  it("content blocks are built correctly for refetched image attachment", async () => {
    const imgData = Buffer.from("fake-png-content");
    const blocks = await resolveAttachmentBlocks([
      {
        mimeType: "image/png",
        fetchData: async () => imgData,
      },
    ]);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].type).toBe("image");
    expect((blocks[0] as any).source.media_type).toBe("image/png");
    expect((blocks[0] as any).source.data).toBe(imgData.toString("base64"));
  });

  it("skips re-fetch when app_mention already has attachments", () => {
    const mentionAttachments = [
      { url: "https://example.com/file.pdf", name: "file.pdf", mimeType: "application/pdf" },
    ];

    // Even if refetched has different data, original takes precedence
    const refetchedAttachments = [
      { url: "https://example.com/other.pdf", name: "other.pdf", mimeType: "application/pdf" },
    ];

    const result = extractAttachmentsFromMention(mentionAttachments, refetchedAttachments);
    expect(result).toHaveLength(1);
    expect(result![0].url).toBe("https://example.com/file.pdf");
  });
});
