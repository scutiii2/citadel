/** True on devices whose primary input cannot hover (phones, tablets). */
export function isTouchOnly(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(hover: none)").matches;
}
