/** The `checked` state of the checkbox that fired `event`. */
export function checked(event: Event): boolean {
  return (event.target as HTMLInputElement).checked;
}
