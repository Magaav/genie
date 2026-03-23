import fs from "node:fs/promises";
import path from "node:path";

const DEFAULT_QUEUE_FILE =
  process.env.FREEWILLER_MEMORY_QUEUE_FILE ||
  "/home/node/.openclaw/workspace/genie-ingest/openclaw-memory-queue.jsonl";
const MAX_TEXT_CHARS = Number.parseInt(process.env.FREEWILLER_MEMORY_BRIDGE_MAX_TEXT_CHARS || "3500", 10);
const recentFingerprints = new Map();

function truncateText(text) {
  if (typeof text !== "string") {
    return "";
  }
  const normalized = text.trim();
  if (normalized.length <= MAX_TEXT_CHARS) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(0, MAX_TEXT_CHARS - 3))}...`;
}

function cleanupFingerprints(now) {
  for (const [key, expiry] of recentFingerprints.entries()) {
    if (expiry <= now) {
      recentFingerprints.delete(key);
    }
  }
}

function shouldSkipDuplicate(fingerprint) {
  const now = Date.now();
  cleanupFingerprints(now);
  const expiry = recentFingerprints.get(fingerprint);
  if (typeof expiry === "number" && expiry > now) {
    return true;
  }
  recentFingerprints.set(fingerprint, now + 60_000);
  return false;
}

function resolveUserText(context) {
  return truncateText(
    context.bodyForAgent ||
      context.transcript ||
      context.body ||
      context.content ||
      "",
  );
}

function resolveAssistantText(context) {
  return truncateText(context.content || "");
}

function normalizeTags(values) {
  return values
    .flatMap((value) => (typeof value === "string" ? [value.trim()] : []))
    .filter(Boolean);
}

function buildCommonMetadata(event) {
  const context = event.context || {};
  return {
    hook_event_type: event.type,
    hook_event_action: event.action,
    session_key: event.sessionKey,
    channel_id: context.channelId || "",
    conversation_id: context.conversationId || "",
    account_id: context.accountId || "",
    message_id: context.messageId || "",
    timestamp: context.timestamp || event.timestamp,
  };
}

async function enqueueEvent(payload) {
  await fs.mkdir(path.dirname(DEFAULT_QUEUE_FILE), { recursive: true });
  await fs.appendFile(DEFAULT_QUEUE_FILE, `${JSON.stringify(payload)}\n`, "utf8");
}

async function handlePreprocessed(event) {
  const context = event.context || {};
  const text = resolveUserText(context);
  if (!text) {
    return;
  }

  const fingerprint = [
    "preprocessed",
    context.channelId || "",
    context.messageId || "",
    context.from || "",
    text,
  ].join("|");
  if (shouldSkipDuplicate(fingerprint)) {
    return;
  }

  await enqueueEvent({
    channel: context.channelId || "openclaw",
    session_id: event.sessionKey || context.conversationId || "",
    role: "user",
    user_id: context.senderId || context.from || "",
    source: "openclaw",
    kind: "conversation",
    tags: normalizeTags([
      "openclaw",
      context.channelId || "",
      "user",
      "preprocessed",
    ]),
    text,
    metadata: {
      ...buildCommonMetadata(event),
      to: context.to || "",
      from: context.from || "",
      sender_name: context.senderName || "",
      sender_username: context.senderUsername || "",
      provider: context.provider || "",
      surface: context.surface || "",
      media_path: context.mediaPath || "",
      media_type: context.mediaType || "",
      transcript_present: typeof context.transcript === "string" && context.transcript.length > 0,
      is_group: Boolean(context.isGroup),
      group_id: context.groupId || "",
      direction: "inbound",
    },
  });
}

async function handleSent(event) {
  const context = event.context || {};
  if (context.success !== true) {
    return;
  }

  const text = resolveAssistantText(context);
  if (!text) {
    return;
  }

  const fingerprint = [
    "sent",
    context.channelId || "",
    context.messageId || "",
    context.to || "",
    text,
  ].join("|");
  if (shouldSkipDuplicate(fingerprint)) {
    return;
  }

  await enqueueEvent({
    channel: context.channelId || "openclaw",
    session_id: event.sessionKey || context.conversationId || "",
    role: "assistant",
    user_id: context.to || "",
    source: "openclaw",
    kind: "conversation",
    tags: normalizeTags([
      "openclaw",
      context.channelId || "",
      "assistant",
      "sent",
    ]),
    text,
    metadata: {
      ...buildCommonMetadata(event),
      to: context.to || "",
      success: true,
      error: context.error || "",
      is_group: Boolean(context.isGroup),
      group_id: context.groupId || "",
      direction: "outbound",
    },
  });
}

export default async function genieMemoryBridge(event) {
  try {
    if (!event || event.type !== "message") {
      return;
    }
    if (event.action === "preprocessed") {
      await handlePreprocessed(event);
      return;
    }
    if (event.action === "sent") {
      await handleSent(event);
    }
  } catch (error) {
    console.error(`[genie-memory-bridge] ${String(error)}`);
  }
}
