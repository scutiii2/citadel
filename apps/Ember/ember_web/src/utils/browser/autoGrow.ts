/** Sizes a textarea to its content, so it grows as the text does. */
export function growToContent(area: HTMLTextAreaElement): void {
  area.style.height = "auto";
  area.style.height = `${area.scrollHeight}px`;
}
