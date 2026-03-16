import type { StateCreator, StoreMutatorIdentifier } from "zustand";

type UndoState<T> = {
  past: T[];
  future: T[];
};

type UndoActions = {
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
};

const MAX_HISTORY = 50;

type WithUndo<T> = T & UndoActions;

type UndoImpl = <
  T extends object,
  Mps extends [StoreMutatorIdentifier, unknown][] = [],
  Mcs extends [StoreMutatorIdentifier, unknown][] = [],
>(
  storeInitializer: StateCreator<T, Mps, Mcs>,
  trackedKeys: (keyof T)[]
) => StateCreator<WithUndo<T>, Mps, Mcs>;

export const undoMiddleware: UndoImpl =
  (config, trackedKeys) => (set, get, api) => {
    const history: UndoState<Record<string, unknown>> = {
      past: [],
      future: [],
    };

    let isUndoRedoing = false;

    const trackedSet: typeof set = (...args) => {
      if (!isUndoRedoing) {
        const currentState = get() as Record<string, unknown>;
        const snapshot: Record<string, unknown> = {};
        for (const key of trackedKeys) {
          snapshot[key as string] = currentState[key as string];
        }
        history.past.push(snapshot);
        if (history.past.length > MAX_HISTORY) {
          history.past.shift();
        }
        history.future = [];
      }
      (set as Function)(...args);
    };

    const initialState = config(trackedSet, get, api);

    return {
      ...initialState,
      undo: () => {
        const prev = history.past.pop();
        if (!prev) return;
        const currentState = get() as Record<string, unknown>;
        const snapshot: Record<string, unknown> = {};
        for (const key of trackedKeys) {
          snapshot[key as string] = currentState[key as string];
        }
        history.future.push(snapshot);
        isUndoRedoing = true;
        (set as Function)(prev);
        isUndoRedoing = false;
      },
      redo: () => {
        const next = history.future.pop();
        if (!next) return;
        const currentState = get() as Record<string, unknown>;
        const snapshot: Record<string, unknown> = {};
        for (const key of trackedKeys) {
          snapshot[key as string] = currentState[key as string];
        }
        history.past.push(snapshot);
        isUndoRedoing = true;
        (set as Function)(next);
        isUndoRedoing = false;
      },
      canUndo: () => history.past.length > 0,
      canRedo: () => history.future.length > 0,
    } as WithUndo<typeof initialState>;
  };
