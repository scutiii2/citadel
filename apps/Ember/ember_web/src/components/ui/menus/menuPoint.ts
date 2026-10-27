/** Where a menu should open, and which button to give focus back to afterwards. */
export interface MenuPoint {
  x: number;
  y: number;
  trigger: HTMLElement | null;
}

/** Opens just under a button, with focus going back to it. */
export function pointBelow(button: HTMLElement | null): MenuPoint {
  const box = button?.getBoundingClientRect();
  return { x: box?.left ?? 0, y: box?.bottom ?? 0, trigger: button };
}

/** Opens where the pointer is, with focus going back to the button. */
export function pointAt(event: MouseEvent, button: HTMLElement | null): MenuPoint {
  return { x: event.clientX, y: event.clientY, trigger: button };
}
