'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { sessionApi } from '@/lib/api/session'
import type { SessionDetail, SSEEventData, SessionFile } from '@/lib/api/types'

export type UseSessionDetailResult = {
  session: SessionDetail | null
  files: SessionFile[]
  events: SSEEventData[]
  loading: boolean
  error: Error | null
  refresh: () => Promise<void>
  refreshFiles: () => Promise<void>
  sendMessage: (message: string, attachmentIds: string[]) => Promise<void>
  streaming: boolean
}

function eventId(event: SSEEventData): string | undefined {
  const data = event.data as { event_id?: string; stream_id?: string }
  return data.event_id || data.stream_id
}

function eventKey(event: SSEEventData): string | undefined {
  const id = eventId(event)
  return id ? `${event.type}:${id}` : undefined
}

export function useSessionDetail(
  sessionId: string | null,
  initialSkipStream = false,
): UseSessionDetailResult {
  const [session, setSession] = useState<SessionDetail | null>(null)
  const [files, setFiles] = useState<SessionFile[]>([])
  const [events, setEvents] = useState<SSEEventData[]>([])
  const [loading, setLoading] = useState(Boolean(sessionId))
  const [error, setError] = useState<Error | null>(null)
  const [streaming, setStreaming] = useState(false)
  const streamCleanupRef = useRef<(() => void) | null>(null)
  const seenEventIdsRef = useRef(new Set<string>())
  const lastEventIdRef = useRef<string | null>(null)
  const skipInitialStreamRef = useRef(initialSkipStream)

  const stopStream = useCallback(() => {
    streamCleanupRef.current?.()
    streamCleanupRef.current = null
  }, [])

  const appendEvent = useCallback((event: SSEEventData) => {
    const id = eventId(event)
    const key = eventKey(event)
    if (key && seenEventIdsRef.current.has(key)) return
    if (key) {
      seenEventIdsRef.current.add(key)
    }
    if (id) {
      lastEventIdRef.current = id
    }

    setEvents((current) => [...current, event])
    setSession((current) => {
      if (!current) return current
      if (event.type === 'title') return { ...current, title: event.data.title }
      if (event.type === 'wait') return { ...current, status: 'waiting' }
      if (event.type === 'done') return { ...current, status: 'completed' }
      if (event.type === 'error') return { ...current, status: 'failed' }
      if (event.type === 'message') {
        return { ...current, latest_message: event.data.message }
      }
      return current.status === 'pending' ? { ...current, status: 'running' } : current
    })

    if (event.type === 'wait' || event.type === 'done' || event.type === 'error') {
      setStreaming(false)
    }
  }, [])

  const refreshFiles = useCallback(async () => {
    if (!sessionId) return
    try {
      setFiles(await sessionApi.getSessionFiles(sessionId))
    } catch (refreshError) {
      console.error('刷新文件列表失败:', refreshError)
    }
  }, [sessionId])

  const refresh = useCallback(async () => {
    if (!sessionId) return
    setError(null)
    try {
      const [detail, currentFiles] = await Promise.all([
        sessionApi.getSessionDetail(sessionId),
        sessionApi.getSessionFiles(sessionId),
      ])
      const history = detail.events ?? []
      seenEventIdsRef.current = new Set(history.map(eventKey).filter((key): key is string => Boolean(key)))
      lastEventIdRef.current = [...history].reverse().map(eventId).find(Boolean) ?? null
      setSession(detail)
      setEvents(history)
      setFiles(currentFiles)
      if (detail.unread_message_count > 0) {
        void sessionApi.clearUnreadMessageCount(sessionId)
      }
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError : new Error('加载失败'))
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => {
    if (!sessionId) return
    const timer = window.setTimeout(() => void refresh(), 0)
    return () => {
      window.clearTimeout(timer)
      stopStream()
    }
  }, [sessionId, refresh, stopStream])

  useEffect(() => {
    if (!sessionId || !session || session.status !== 'running') return
    if (skipInitialStreamRef.current || streamCleanupRef.current) return

    setStreaming(true)
    streamCleanupRef.current = sessionApi.chat(
      sessionId,
      { event_id: lastEventIdRef.current || undefined },
      appendEvent,
      (streamError) => {
        streamCleanupRef.current = null
        setStreaming(false)
        if (streamError.message === 'SSE_STREAM_END') {
          void refresh()
          return
        }
        setError(streamError)
      },
    )
    return stopStream
  }, [appendEvent, refresh, session, sessionId, stopStream])

  const sendMessage = useCallback(async (message: string, attachmentIds: string[]) => {
    if (!sessionId) return
    stopStream()
    skipInitialStreamRef.current = false
    setError(null)
    setStreaming(true)
    setSession((current) => current ? { ...current, status: 'running' } : current)

    streamCleanupRef.current = sessionApi.chat(
      sessionId,
      { message, attachments: attachmentIds },
      appendEvent,
      (streamError) => {
        streamCleanupRef.current = null
        setStreaming(false)
        if (streamError.message === 'SSE_STREAM_END') {
          void refresh()
          return
        }
        setError(streamError)
      },
    )
  }, [appendEvent, refresh, sessionId, stopStream])

  return {
    session,
    files,
    events,
    loading,
    error,
    refresh,
    refreshFiles,
    sendMessage,
    streaming,
  }
}
