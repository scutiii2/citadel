/** One line of a popup menu. `children` makes it open a flyout. */
export interface MenuItem {
  id: string;
  label: string;
  checked?: boolean;
  danger?: boolean;
  disabled?: boolean;
  separator?: boolean;
  children?: MenuItem[];
}
