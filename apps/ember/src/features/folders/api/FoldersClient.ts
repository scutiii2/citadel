import { ApiError, apiRequest } from "../../../api/http";
import { apiUrl, credentialsMode } from "../../../utils/server";

/** Longest a folder lives, in minutes (the server enforces it). */
export const FOLDER_MAX_MINUTES = 60;

export interface FolderFile {
  id: number;
  name: string;
  size: number;
  created_at: string;
}

/** A folder as its owner sees it, link token included. Times are UTC. */
export interface Folder {
  id: number;
  name: string;
  token: string;
  created_at: string;
  expires_at: string;
  files: FolderFile[];
}

/** What anyone with the link sees: no owner, no token. */
export interface PublicFolder {
  name: string;
  expires_at: string;
  max_file_bytes: number;
  files: FolderFile[];
}

const link = (token: string) => `/api/folder-links/${encodeURIComponent(token)}`;

/** The owner's routes need folders.use. The link routes (`read`, `add`, `downloadUrl`) need no login. */
export const foldersClient = {
  list: () => apiRequest<Folder[]>("GET", "/api/shared-folders"),
  create: (name: string, minutes: number) => apiRequest<Folder>("POST", "/api/shared-folders", { name, minutes }),
  remove: (id: number) => apiRequest<void>("DELETE", `/api/shared-folders/${id}`),
  removeFile: (id: number, fileId: number) => apiRequest<void>("DELETE", `/api/shared-folders/${id}/files/${fileId}`),

  read: (token: string) => apiRequest<PublicFolder>("GET", link(token)),
  /** The file as the request body (streamed, not multipart); the server refuses a file over its cap. */
  async add(token: string, file: File): Promise<FolderFile> {
    const response = await fetch(apiUrl(`${link(token)}/files?name=${encodeURIComponent(file.name)}`), {
      method: "PUT",
      body: file,
      credentials: credentialsMode(),
    });
    const data = (await response.json().catch(() => null)) as (FolderFile & { detail?: unknown }) | null;
    if (!response.ok) throw new ApiError(response.status, typeof data?.detail === "string" ? data.detail : response.statusText);
    return data as FolderFile;
  },
  downloadUrl: (token: string, fileId: number) => apiUrl(`${link(token)}/files/${fileId}`),
};
