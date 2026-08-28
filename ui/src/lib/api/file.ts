import { API_BASE_URL, get, post } from "./fetch";
import type { FileInfo, FileUploadParams } from "./types";

/**
 * 文件模块 API
 */
export const fileApi = {
  /**
   * 上传文件
   * @param params 上传参数，包含文件和可选的会话 ID
   * @returns 文件信息
   */
  uploadFile: async (params: FileUploadParams): Promise<FileInfo> => {
    const formData = new FormData();
    formData.append("file", params.file);
    
    if (params.session_id) {
      formData.append("session_id", params.session_id);
    }

    const file = await post<FileInfo>("/files", formData);
    return { ...file, content_type: file.content_type || file.mime_type || "application/octet-stream" };
  },

  /**
   * 获取文件信息
   * @param fileId 文件 ID
   * @returns 文件信息
   */
  getFileInfo: (fileId: string): Promise<FileInfo> => {
    return get<FileInfo>(`/files/${fileId}`);
  },

  /**
   * 下载文件
   * @param fileId 文件 ID
   * @returns Blob 对象
   */
  downloadFile: async (fileId: string): Promise<Blob> => {
    const generated = parseGeneratedFileId(fileId);
    const url = generated
      ? `${API_BASE_URL}/sessions/${encodeURIComponent(generated.sessionId)}/files/download?filepath=${encodeURIComponent(generated.filepath)}`
      : `${API_BASE_URL}/files/${encodeURIComponent(fileId)}/download`;
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`下载失败: ${response.statusText}`);
    }

    return response.blob();
  },

  /**
   * 下载文件并获取 URL（用于直接下载或预览）
   * @param fileId 文件 ID
   * @returns 文件下载 URL
   */
  getFileDownloadUrl: (fileId: string): string => {
    const generated = parseGeneratedFileId(fileId);
    return generated
      ? `${API_BASE_URL}/sessions/${encodeURIComponent(generated.sessionId)}/files/download?filepath=${encodeURIComponent(generated.filepath)}`
      : `${API_BASE_URL}/files/${encodeURIComponent(fileId)}/download`;
  },
};

function parseGeneratedFileId(fileId: string): { sessionId: string; filepath: string } | null {
  if (!fileId.startsWith("generated:")) return null;
  const separator = fileId.indexOf(":", "generated:".length);
  if (separator < 0) return null;
  try {
    return {
      sessionId: decodeURIComponent(fileId.slice("generated:".length, separator)),
      filepath: decodeURIComponent(fileId.slice(separator + 1)),
    };
  } catch {
    return null;
  }
}
