import { flushSync } from 'react-dom';

const FLIP_SELECTOR = '[data-flip-id]';

export function captureFlipPositions(root: ParentNode = document): Map<string, DOMRect> {
  const map = new Map<string, DOMRect>();
  root.querySelectorAll(FLIP_SELECTOR).forEach((el) => {
    const id = el.getAttribute('data-flip-id');
    if (id) {
      map.set(id, el.getBoundingClientRect());
    }
  });
  return map;
}

export function playFlipAnimation(
  before: Map<string, DOMRect>,
  root: ParentNode = document
): void {
  root.querySelectorAll(FLIP_SELECTOR).forEach((el) => {
    const id = el.getAttribute('data-flip-id');
    if (!id) return;

    const first = before.get(id);
    if (!first) return;

    const node = el as HTMLElement;
    const last = node.getBoundingClientRect();
    const deltaX = first.left - last.left;
    const deltaY = first.top - last.top;

    if (Math.abs(deltaX) < 0.5 && Math.abs(deltaY) < 0.5) return;

    node.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
    node.style.transition = 'transform 0s';

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        node.style.transition = 'transform 0.38s cubic-bezier(0.4, 0, 0.2, 1)';
        node.style.transform = '';
      });
    });
  });
}

export function runFlipUpdate(root: ParentNode | null, update: () => void): void {
  const scope = root ?? document;
  const before = captureFlipPositions(scope);
  flushSync(update);
  requestAnimationFrame(() => {
    playFlipAnimation(before, scope);
  });
}
