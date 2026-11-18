/**
 * The report's print layout for the in-app Print, which prints a frame where the report's own
 * scripts do not run: the same rule as the report's `beforeprint` script (render.py,
 * PRINT_LAYOUT_JS). A text-and-figure row that would cross a page boundary keeps its text on
 * the page and its figure moves to just after the break, so no part-page is left blank.
 * Positions are measured on the body sheet, which has the printed width (174 mm) on screen.
 */
export function layOutForPrint(doc: Document): number {
  const body = doc.querySelector<HTMLElement>(".r-body");
  if (!body || body.dataset.laid) return 0;
  body.dataset.laid = "1";
  const mm = (value: number) => {
    const probe = doc.createElement("div");
    probe.style.cssText = `position:absolute;visibility:hidden;height:${value}mm`;
    doc.body.appendChild(probe);
    const height = probe.getBoundingClientRect().height;
    probe.remove();
    return height;
  };
  const page = mm(257);
  const origin = body.getBoundingClientRect().top + mm(20);
  const flat = () => {
    const out: Element[] = [];
    body.querySelectorAll(".r-section, .r-group").forEach((el) => {
      if (el.classList.contains("r-group")) out.push(el);
      else out.push(...Array.from(el.children));
    });
    return out;
  };
  let moves = 0;
  for (let pass = 0; pass < 40; pass++) {
    const items = flat();
    let shift = 0;
    let moved = false;
    for (let i = 0; i < items.length && !moved; i++) {
      const block = items[i];
      const rect = block.getBoundingClientRect();
      if (!block.matches(".r-row:not(.r-row-split), figure, .r-watch") || rect.height >= page) continue;
      const y = rect.top - origin + shift;
      const end = Math.ceil((y + 1) / page) * page;
      if (y + rect.height <= end) continue;
      const figure = block.matches(".r-row:not(.r-row-split)") ? block.querySelector(":scope > figure") : null;
      if (!figure || !block.querySelector(":scope > .r-text")) {
        shift += end - y;
        continue;
      }
      block.classList.add("r-row-split");
      const limit = end - shift;
      let after = block;
      for (let j = i + 1; j < items.length; j++) {
        const next = items[j].getBoundingClientRect();
        if (next.top - origin + next.height > limit || items[j].matches(".r-group")) break;
        after = items[j];
      }
      const holder = doc.createElement("div");
      holder.className = "r-row r-row-moved";
      holder.appendChild(figure);
      after.parentNode?.insertBefore(holder, after.nextSibling);
      moved = true;
      moves += 1;
    }
    if (!moved) break;
  }
  return moves;
}
