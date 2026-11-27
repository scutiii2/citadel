/** A file dropped outside every drop zone would otherwise be opened by the browser, replacing the app with it.
 * Drop zones are left alone: they have already called `preventDefault`. Returns what removes the guard. */
export function installFileDropGuard(target: Window = window): () => void {
  const refuse = (event: DragEvent): void => {
    if (event.defaultPrevented || !event.dataTransfer?.types.includes("Files")) return;
    if (event.target instanceof HTMLInputElement && event.target.type === "file") return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "none";
  };
  target.addEventListener("dragover", refuse);
  target.addEventListener("drop", refuse);
  return () => {
    target.removeEventListener("dragover", refuse);
    target.removeEventListener("drop", refuse);
  };
}
