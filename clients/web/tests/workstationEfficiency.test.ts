import assert from "node:assert/strict";
import test from "node:test";
import { workspaceShortcutCommand, isPaletteShortcut } from "../src/app/experience/commandPalette.ts";

test("physical primary shortcuts navigate on Ctrl or Command without relying on shifted glyph", () => {
  assert.equal(workspaceShortcutCommand({key: "!", code: "Digit1", ctrlKey: true, shiftKey: true}, false), "navigate.primary.market");
  assert.equal(workspaceShortcutCommand({key: "#", code: "Digit3", metaKey: true, shiftKey: true}, false), "navigate.primary.strategy");
  assert.equal(workspaceShortcutCommand({key: "6", code: "Digit6", ctrlKey: true, shiftKey: true}, false), "navigate.primary.administration");
});
test("navigation never steals editing, IME, repeating keys or unrelated modifier chords", () => {
  const event = {key: "1", code: "Digit1", ctrlKey: true, shiftKey: true};
  assert.equal(workspaceShortcutCommand(event, true), null);
  for (const override of [{isComposing:true}, {repeat:true}, {altKey:true}, {shiftKey:false}, {ctrlKey:false}, {code:"Digit9"}]) {
    assert.equal(workspaceShortcutCommand({...event,...override}, false), null);
  }
  assert.equal(isPaletteShortcut({key:"k",ctrlKey:true,isComposing:true}),false);
  assert.equal(isPaletteShortcut({key:"k",ctrlKey:true,repeat:true}),false);
});
