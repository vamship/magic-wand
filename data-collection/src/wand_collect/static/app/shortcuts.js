// Keyboard shortcuts. The key for each action comes from the application
// settings (`shortcuts`), so it can be changed in the configuration. Keys
// 1 to 9 always choose a label. Keys typed into an input field are ignored.

const DISPLAY = {
  Escape: "Esc",
  ArrowLeft: "←",
  ArrowRight: "→",
  ArrowUp: "↑",
  ArrowDown: "↓",
  Backspace: "⌫",
  Delete: "Del",
  Enter: "↵",
  " ": "Space",
};

// How a key is shown on a button.
export function keyLabel(key) {
  if (key in DISPLAY) return DISPLAY[key];
  return key.length === 1 ? key.toUpperCase() : key;
}

function isTyping(target) {
  if (!target) return false;
  const tag = (target.tagName || "").toLowerCase();
  return (
    tag === "input" ||
    tag === "textarea" ||
    tag === "select" ||
    Boolean(target.isContentEditable)
  );
}

export function createShortcuts(bindings = {}) {
  let keys = { ...bindings };
  const handlers = new Map(); // action -> list of functions

  function run(action, argument) {
    const list = handlers.get(action) || [];
    list.forEach((handler) => handler(argument));
    return list.length > 0;
  }

  return {
    setBindings(next) {
      keys = { ...next };
    },
    // The key bound to an action, for showing on its button.
    keyFor(action) {
      return keys[action] === undefined ? "" : keyLabel(keys[action]);
    },
    // Registers a handler for an action; returns a function that removes it.
    on(action, handler) {
      const list = handlers.get(action) || [];
      handlers.set(action, [...list, handler]);
      return () => {
        handlers.set(
          action,
          (handlers.get(action) || []).filter((h) => h !== handler),
        );
      };
    },
    // Handles a keyboard event; returns true if it was a shortcut.
    handle(event) {
      if (isTyping(event.target)) return false;
      if (event.ctrlKey || event.metaKey || event.altKey) return false;
      if (/^[1-9]$/.test(event.key)) {
        return run("label", Number(event.key));
      }
      const action = Object.keys(keys).find(
        (name) => keys[name].toLowerCase() === event.key.toLowerCase(),
      );
      return action ? run(action) : false;
    },
    attach(target = window) {
      const listener = (event) => {
        if (this.handle(event)) event.preventDefault();
      };
      target.addEventListener("keydown", listener);
      return () => target.removeEventListener("keydown", listener);
    },
  };
}
