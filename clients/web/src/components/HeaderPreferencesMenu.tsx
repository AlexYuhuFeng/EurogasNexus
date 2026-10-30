import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { CurrentUserDTO } from "@/api/client";
import type { ThemeMode } from "@/stores/theme";
import { LOCALES } from "@/i18n/locales";
import { isShortcutHelpKey, KeyboardShortcutsDialog } from "./KeyboardShortcutsDialog";

/** "Jane Smith" → "JS"; a single name gives its first two letters. */
export function accountInitials(name: string): string {
  const parts = name.trim().split(/[\s._-]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const letters = parts.length === 1 ? parts[0].slice(0, 2) : `${parts[0][0]}${parts[parts.length - 1][0]}`;
  return letters.toUpperCase();
}

type Translate = (key: string) => string;

interface HeaderPreferencesMenuProps {
  currentUser: CurrentUserDTO;
  language: string;
  mode: ThemeMode;
  t: Translate;
  onLanguageChange: (language: string) => void;
  onModeChange: (mode: ThemeMode) => void;
  onOpenSettings: () => void;
  onOpenAccess: () => void;
  onSignOut: () => void;
}

export function HeaderPreferencesMenu({
  currentUser,
  language,
  mode,
  t,
  onLanguageChange,
  onModeChange,
  onOpenSettings,
  onOpenAccess,
  onSignOut,
}: HeaderPreferencesMenuProps) {
  const [open, setOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const displayName = currentUser.display_name ?? currentUser.name;
  const closeShortcuts = useCallback(() => setShortcutsOpen(false), []);

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (isShortcutHelpKey(event)) {
        event.preventDefault();
        setShortcutsOpen(true);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const focusableItems = () =>
    Array.from(
      menuRef.current?.querySelectorAll<HTMLButtonElement>(
        '[role="menuitem"]:not(:disabled), [role="menuitemradio"]:not(:disabled)',
      ) ?? [],
    );

  /**
   * Close the menu and put focus back on the trigger that opened it.
   *
   * The focus move is synchronous and happens *before* the menu closes: the trigger is always
   * mounted, so focusing it does not depend on a frame having run, and closing afterwards cannot
   * drop focus into the document body because the element that holds focus is not inside the
   * subtree being removed. The accessibility sweep asserts exactly this outcome right after
   * `Escape`, which a deferred focus cannot promise.
   */
  const closeAndReturnFocus = () => {
    triggerRef.current?.focus();
    setOpen(false);
  };

  const select = (action: () => void) => {
    action();
    closeAndReturnFocus();
  };

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    /**
     * Escape closes the menu from anywhere while it is open.
     *
     * The menu's own `onKeyDown` only sees an Escape that reaches it, which requires focus to be
     * inside the popover already - and the popover moves focus into itself on the next frame. A user
     * (or an acceptance sweep) that presses Escape in that window would otherwise leave the menu
     * open with focus on the document body. Closing on the document covers every position inside the
     * open menu, which is what the ARIA menu-button pattern asks for: Escape dismisses the menu and
     * focus returns to the trigger.
     */
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeAndReturnFocus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    window.requestAnimationFrame(() => focusableItems()[0]?.focus());
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const onMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeAndReturnFocus();
      return;
    }
    const items = focusableItems();
    if (items.length === 0) return;
    const current = Math.max(0, items.indexOf(document.activeElement as HTMLButtonElement));
    let next: number | null = null;
    if (event.key === "ArrowDown") next = (current + 1) % items.length;
    if (event.key === "ArrowUp") next = (current - 1 + items.length) % items.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = items.length - 1;
    if (next === null) return;
    event.preventDefault();
    items[next]?.focus();
  };

  return (
    <div className="topbar-preferences-menu" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className="topbar-preferences-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="topbar-preferences-menu"
        aria-label={`${t("topbar.account_menu")}: ${displayName}`}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="topbar-account-avatar" aria-hidden="true">{accountInitials(displayName)}</span>
        <span className="topbar-account-name">{displayName}</span>
      </button>
      {open && (
        <div
          id="topbar-preferences-menu"
          className="topbar-preferences-popover"
          role="menu"
          aria-label={t("topbar.preferences_menu")}
          ref={menuRef}
          onKeyDown={onMenuKeyDown}
        >
          <div className="topbar-menu-identity">
            <strong>{displayName}</strong>
            <span>
              {currentUser.role}
              {currentUser.experience?.office ? ` · ${currentUser.experience.office}` : ""}
            </span>
          </div>

          <div className="topbar-menu-group" role="group" aria-label={t("settings.language")}>
            <span className="topbar-menu-group-label">{t("settings.language")}</span>
            {LOCALES.map((locale) => (
              <button
                key={locale.code}
                type="button"
                role="menuitemradio"
                lang={locale.code}
                aria-checked={language.toLowerCase() === locale.code.toLowerCase()}
                onClick={() => select(() => onLanguageChange(locale.code))}
              >
                {locale.nativeName}
              </button>
            ))}
          </div>

          <div className="topbar-menu-group" role="group" aria-label={t("settings.appearance")}>
            <span className="topbar-menu-group-label">{t("settings.appearance")}</span>
            {(["system", "light", "dark"] as ThemeMode[]).map((themeMode) => (
              <button
                key={themeMode}
                type="button"
                role="menuitemradio"
                aria-checked={mode === themeMode}
                onClick={() => select(() => onModeChange(themeMode))}
              >
                {t(`theme.${themeMode}`)}
              </button>
            ))}
          </div>

          <div className="topbar-menu-group lifecycle" role="group" aria-label={t("topbar.account_actions")}>
            <span className="topbar-menu-group-label">{t("topbar.account_actions")}</span>
            <button type="button" role="menuitem" onClick={() => select(onOpenSettings)}>
              {t("topbar.open_settings")}
            </button>
            <button type="button" role="menuitem" onClick={() => select(() => setShortcutsOpen(true))}>
              {t("topbar.keyboard_shortcuts")} <kbd>?</kbd>
            </button>
            {currentUser.permissions.includes("identity.manage") && (
              <button type="button" role="menuitem" onClick={() => select(onOpenAccess)}>
                {t("topbar.access_identity")}
              </button>
            )}
            <button type="button" role="menuitem" onClick={() => {
              triggerRef.current?.focus();
              setOpen(false);
              onSignOut();
            }}>
              {t("topbar.sign_out")}
            </button>
          </div>
        </div>
      )}
      <KeyboardShortcutsDialog open={shortcutsOpen} onClose={closeShortcuts} t={t} />
    </div>
  );
}
