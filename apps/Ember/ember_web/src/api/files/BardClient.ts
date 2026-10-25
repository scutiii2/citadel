import { apiRequest } from "../http";

export interface SpeechClip {
  file_id: string;
  duration_s: number;
  voice: string;
}

export const bardClient = {
  voices(signal?: AbortSignal): Promise<{ voices: string[] }> {
    return apiRequest("GET", "/api/bard/voices", undefined, undefined, signal);
  },
  speak(text: string, voice: string, signal?: AbortSignal): Promise<SpeechClip> {
    return apiRequest("POST", "/api/bard/speak", { text, voice }, undefined, signal);
  },
};
