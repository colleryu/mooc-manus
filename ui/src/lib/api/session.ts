import { API_BASE_URL, del, get, post } from "./fetch";
import type {
  ChatMessage,
  ChatParams,
  CreateSessionParams,
  PlanEvent,
  Session,
  SessionDetail,
  SessionFile,
  SessionsData,
  SSEEventData,
  SSEEventHandler,
  StepEvent,
  ToolEvent,
} from "./types";

type RawRecord = Record<string, unknown>;

function asRecord(value: unknown): RawRecord {
  return value && typeof value === "object" ? value as RawRecord : {};
}

function normalizeSession(raw: unknown): SessionDetail {
  const value = asRecord(raw);
  const rawEvents = Array.isArray(value.events) ? value.events : [];
  return {
    ...value,
    id: typeof value.id === "string" ? value.id : undefined,
    session_id: String(value.session_id ?? value.id ?? ""),
    title: String(value.title ?? ""),
    latest_message: String(value.latest_message ?? ""),
    latest_message_at: typeof value.latest_message_at === "string" ? value.latest_message_at : null,
    status: (value.status ?? "pending") as Session["status"],
    unread_message_count: Number(value.unread_message_count ?? 0),
    events: rawEvents
      .map((event) => normalizeBackendEvent(event))
      .filter((event): event is SSEEventData => event !== null),
  } as SessionDetail;
}

function normalizeAttachment(raw: unknown): NonNullable<ChatMessage["attachments"]>[number] {
  const value = asRecord(raw);
  return {
    ...value,
    file_id: String(value.file_id ?? value.id ?? ""),
    filename: String(value.filename ?? ""),
    size: Number(value.size ?? 0),
  };
}

export function normalizeBackendEvent(raw: unknown, streamId?: string): SSEEventData | null {
  const event = asRecord(raw);
  const type = typeof event.type === "string" ? event.type : "";
  const common = {
    event_id: String(event.id ?? ""),
    stream_id: streamId || undefined,
    task_id: event.task_id,
    created_at: event.create_at,
  };

  switch (type) {
    case "message":
      return {
        type,
        data: {
          ...common,
          role: event.role === "user" ? "user" : "assistant",
          message: String(event.message ?? ""),
          attachments: Array.isArray(event.attachments)
            ? event.attachments.map(normalizeAttachment)
            : [],
        },
      };
    case "title":
      return { type, data: { ...common, title: String(event.title ?? "") } };
    case "plan": {
      const plan = asRecord(event.plan);
      return { type, data: { ...plan, ...common, steps: Array.isArray(plan.steps) ? plan.steps : [] } as PlanEvent };
    }
    case "step": {
      const step = asRecord(event.step);
      return {
        type,
        data: {
          ...step,
          ...common,
          id: String(step.id ?? event.id ?? ""),
          description: String(step.description ?? ""),
          status: String(step.status ?? event.status ?? "pending"),
        } as StepEvent,
      };
    }
    case "tool":
      const toolContent = asRecord(event.tool_content);
      const screenshot = typeof toolContent.screenshot === "string" && toolContent.screenshot
        ? `${API_BASE_URL}/files/${encodeURIComponent(toolContent.screenshot)}/download`
        : undefined;
      return {
        type,
        data: {
          ...common,
          tool_call_id: String(event.tool_call_id ?? event.id ?? ""),
          name: String(event.tool_name ?? ""),
          function: String(event.function_name ?? ""),
          args: asRecord(event.function_args),
          content: screenshot ? { ...toolContent, screenshot } : event.tool_content ?? event.function_result,
          status: event.status,
        } as ToolEvent,
      };
    case "wait":
    case "done":
      return { type, data: common } as SSEEventData;
    case "error":
      return { type, data: { ...common, error: String(event.error ?? "任务执行失败") } };
    default:
      return null;
  }
}

function generatedFileId(sessionId: string, filepath: string): string {
  return `generated:${encodeURIComponent(sessionId)}:${encodeURIComponent(filepath)}`;
}

function normalizeSessionFile(sessionId: string, raw: unknown): SessionFile {
  const value = asRecord(raw);
  const filepath = String(value.filepath ?? "");
  const filename = String(value.filename ?? filepath.split("/").pop() ?? "");
  return {
    ...value,
    id: typeof value.id === "string" && value.id
      ? value.id
      : generatedFileId(sessionId, filepath),
    filename,
    filepath,
    key: String(value.key ?? ""),
    extension: String(value.extension ?? filename.split(".").pop() ?? ""),
    content_type: String(value.content_type ?? value.mime_type ?? "application/octet-stream"),
    mime_type: typeof value.mime_type === "string" ? value.mime_type : undefined,
    size: Number(value.size ?? 0),
  };
}

function eventSourceUrl(sessionId: string, after?: string): string {
  const url = new URL(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}/events`);
  if (after) url.searchParams.set("after", after);
  return url.toString();
}

export const sessionApi = {
  getSessions: async (): Promise<SessionsData> => {
    const raw = await get<unknown>("/sessions");
    const values = Array.isArray(raw)
      ? raw
      : Array.isArray(asRecord(raw).sessions) ? asRecord(raw).sessions as unknown[] : [];
    return { sessions: values.map(normalizeSession) };
  },

  createSession: async (params?: CreateSessionParams): Promise<Session> => {
    return normalizeSession(await post<unknown>("/sessions", params || {}));
  },

  streamSessions: (
    onSessions: (sessions: Session[]) => void,
    onError?: (error: Error) => void,
  ): (() => void) => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const result = await sessionApi.getSessions();
        if (!stopped) onSessions(result.sessions);
      } catch (error) {
        if (!stopped) onError?.(error instanceof Error ? error : new Error("获取会话列表失败"));
      } finally {
        if (!stopped) timer = setTimeout(poll, 5000);
      }
    };
    timer = setTimeout(poll, 5000);
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  },

  getSession: async (sessionId: string): Promise<Session> => {
    return normalizeSession(await get<unknown>(`/sessions/${encodeURIComponent(sessionId)}`));
  },

  getSessionDetail: async (sessionId: string): Promise<SessionDetail> => {
    return normalizeSession(await get<unknown>(`/sessions/${encodeURIComponent(sessionId)}`));
  },

  chat: (
    sessionId: string,
    params: ChatParams,
    onEvent: SSEEventHandler,
    onError?: (error: Error) => void,
  ): (() => void) => {
    let stopped = false;
    let source: EventSource | null = null;

    const start = async () => {
      try {
        if (params.message !== undefined || (params.attachments?.length ?? 0) > 0) {
          const updated = normalizeSession(await post<unknown>(
            `/sessions/${encodeURIComponent(sessionId)}/messages`,
            { message: params.message ?? "", attachments: params.attachments ?? [] },
            { timeout: 5 * 60 * 1000 },
          ));
          const userEvent = [...(updated.events ?? [])].reverse().find(
            (event) => event.type === "message" && event.data.role === "user",
          );
          if (!stopped && userEvent) onEvent(userEvent);
        }

        if (stopped) return;
        source = new EventSource(eventSourceUrl(sessionId, params.event_id));
        const eventTypes = ["message", "title", "plan", "step", "tool", "wait", "done", "error"] as const;
        for (const eventType of eventTypes) {
          source.addEventListener(eventType, (messageEvent) => {
            if (stopped || !(messageEvent instanceof MessageEvent)) return;
            try {
              const normalized = normalizeBackendEvent(JSON.parse(messageEvent.data), messageEvent.lastEventId);
              if (normalized) onEvent(normalized);
              if (eventType === "done" || eventType === "error") source?.close();
            } catch (error) {
              onError?.(error instanceof Error ? error : new Error("事件解析失败"));
            }
          });
        }
        source.onerror = () => {
          if (stopped) return;
          source?.close();
          onError?.(new Error("SSE_STREAM_END"));
        };
      } catch (error) {
        if (!stopped) onError?.(error instanceof Error ? error : new Error("启动任务流失败"));
      }
    };

    void start();
    return () => {
      stopped = true;
      source?.close();
    };
  },

  stopSession: (sessionId: string): Promise<void> =>
    post<void>(`/sessions/${encodeURIComponent(sessionId)}/cancel`, {}),

  deleteSession: (sessionId: string): Promise<void> =>
    del<void>(`/sessions/${encodeURIComponent(sessionId)}`),

  clearUnreadMessageCount: (sessionId: string): Promise<void> =>
    post<void>(`/sessions/${encodeURIComponent(sessionId)}/read`, {}),

  getSessionFiles: async (sessionId: string): Promise<SessionFile[]> => {
    const raw = await get<unknown>(`/sessions/${encodeURIComponent(sessionId)}/files`);
    const files = Array.isArray(raw)
      ? raw
      : Array.isArray(asRecord(raw).files) ? asRecord(raw).files as unknown[] : [];
    return files.map((file) => normalizeSessionFile(sessionId, file));
  },
};
