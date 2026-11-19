import { useCallback, useEffect, useMemo, useState } from "react";

import { api, type TradingBookInput, type TradingBooksDTO } from "@/api/client";
import { DataGrid, RecordPicker, type DataGridColumn, type RecordOption } from "@/components/ui";
import { idFromName } from "@/components/ui/recordPickerModel";
import { contractOptions } from "@/app/model/recordOptions";
import { REPORTING_CURRENCIES } from "@/app/time/valueFormat";
import { useApiStore } from "@/stores/api";

type BookRow = TradingBooksDTO["books"][number];

type Translate = (key: string, options?: Record<string, unknown>) => string;

const REGIONS = ["europe", "north_america", "asia", "global"];
const EMPTY: TradingBookInput & { book_id: string; members: string } = {
  book_id: "",
  name: "",
  legal_entity: "",
  region: "europe",
  business: "",
  base_currency: "EUR",
  members: "",
};

/**
 * Trading books by legal entity, region and business: what head office, a region or a desk
 * rolls positions up by. Middle office defines books and assigns contracts and trades.
 */
export function TradingBooksPanel({ t }: { t: Translate }) {
  const [books, setBooks] = useState<TradingBooksDTO | null>(null);
  const [draft, setDraft] = useState(EMPTY);
  const [message, setMessage] = useState<string | null>(null);
  // The live principle (UX_REFERENCE rule 25): books, entities and contracts are chosen from
  // what exists; a new book's id is made from its name.
  const contracts = useApiStore((state) => state.upstreamContracts);
  const bookChoices = useMemo<RecordOption[]>(
    () => (books?.books ?? []).map((book) => ({ id: book.book_id, label: book.name, detail: [book.legal_entity, book.business].filter(Boolean).join(" · ") })),
    [books],
  );
  const distinct = (values: string[]): RecordOption[] => [...new Set(values.filter(Boolean))].map((value) => ({ id: value, label: value }));
  const entityChoices = useMemo(() => distinct((books?.books ?? []).map((book) => book.legal_entity)), [books]);
  const businessChoices = useMemo(() => distinct((books?.books ?? []).map((book) => book.business)), [books]);
  const contractChoices = useMemo(() => contractOptions(contracts), [contracts]);
  const pickBook = (choice: { id: string; manual: boolean } | null) => {
    if (!choice) return;
    if (choice.manual) {
      setDraft({ ...EMPTY, book_id: idFromName(choice.id, bookChoices.map((item) => item.id)), name: choice.id });
      return;
    }
    const book = books?.books.find((item) => item.book_id === choice.id);
    if (book) {
      setDraft({ ...EMPTY, book_id: book.book_id, name: book.name, legal_entity: book.legal_entity, region: book.region, business: book.business, base_currency: book.base_currency });
    }
  };
  const load = useCallback(() => {
    api.tradingBooks().then((response) => setBooks(response.data)).catch(() => setBooks(null));
  }, []);
  useEffect(load, [load]);

  const save = () => {
    const { book_id: bookId, members, ...body } = draft;
    const ids = members.split(/[\s,]+/).filter(Boolean);
    api
      .saveTradingBook(bookId.trim(), { ...body, contract_ids: ids, order_ids: ids })
      .then((response) => {
        setMessage(t("books.saved", {
          contracts: response.data.contracts_assigned,
          orders: response.data.orders_assigned,
        }));
        setDraft(EMPTY);
        load();
      })
      .catch((caught: unknown) => setMessage(caught instanceof Error ? caught.message : String(caught)));
  };
  const field = (key: keyof typeof draft) => (event: { target: { value: string } }) =>
    setDraft({ ...draft, [key]: event.target.value });

  const bookColumns = useMemo<DataGridColumn<BookRow>[]>(
    () => [
      { id: "entity", header: t("books.legal_entity"), sortable: true, value: (book) => book.legal_entity },
      { id: "region", header: t("books.region"), sortable: true, value: (book) => t(`books.region_${book.region}`) },
      { id: "business", header: t("books.business"), sortable: true, value: (book) => book.business },
      {
        id: "book",
        header: t("books.book"),
        rowHeader: true,
        sortable: true,
        value: (book) => book.name,
        render: (book) => (
          <>
            {book.name} <small className="ds-grid-unit">{book.book_id} · {book.base_currency}</small>
          </>
        ),
      },
      { id: "contracts", header: t("books.contracts"), type: "number", sortable: true, value: (book) => book.contracts },
      { id: "orders", header: t("books.orders"), type: "number", sortable: true, value: (book) => book.orders },
    ],
    [t],
  );

  return (
    <section className="workspace-panel span-3 trading-books-panel" aria-labelledby="trading-books-title">
      <h2 id="trading-books-title">{t("books.title")}</h2>
      {books && books.books.length === 0 && <p className="muted">{t("books.empty")}</p>}
      {books && books.books.length > 0 && (
        <DataGrid
          id="trading-books"
          label={t("books.title")}
          columns={bookColumns}
          rows={books.books}
          rowKey={(book) => book.book_id}
          density="compact"
          rowAttributes={() => ({ "data-record": "trading-book" })}
          tableAttributes={{ "data-trading-books": "true" }}
        />
      )}
      {books && (books.unassigned.contracts > 0 || books.unassigned.orders > 0) && (
        <p className="muted">{t("books.unassigned", books.unassigned)}</p>
      )}
      {/* Adding a book is occasional set-up, not a reading: folded under its action (#69). */}
      <details className="scope-fold">
        <summary>{t("books.add")}</summary>
      <div className="licence-form">
        <RecordPicker id="book" label={t("books.book")} options={books ? bookChoices : null} value={draft.book_id || null} allowManual onChange={pickBook} />
        <label><span>{t("books.name")}</span><input value={draft.name} onChange={field("name")} /></label>
        <RecordPicker
          id="book-entity"
          label={t("books.legal_entity")}
          options={books ? entityChoices : null}
          value={draft.legal_entity || null}
          allowManual
          onChange={(choice) => setDraft({ ...draft, legal_entity: choice?.id ?? "" })}
        />
        <label>
          <span>{t("books.region")}</span>
          <select value={draft.region} onChange={field("region")}>
            {REGIONS.map((region) => <option key={region} value={region}>{t(`books.region_${region}`)}</option>)}
          </select>
        </label>
        <RecordPicker
          id="book-business"
          label={t("books.business")}
          options={books ? businessChoices : null}
          value={draft.business || null}
          allowManual
          onChange={(choice) => setDraft({ ...draft, business: choice?.id ?? "" })}
        />
        <label><span>{t("books.base_currency")}</span>
          <select value={draft.base_currency} onChange={field("base_currency")}>
            {REPORTING_CURRENCIES.map((code) => <option key={code} value={code}>{code}</option>)}
          </select>
        </label>
        <RecordPicker
          id="book-contracts"
          label={t("books.members")}
          multiple
          options={contractChoices}
          value={draft.members.split(/[\s,]+/).filter(Boolean)}
          onChange={(ids) => setDraft({ ...draft, members: ids.join(",") })}
        />
        <button
          type="button"
          disabled={!draft.book_id.trim() || !draft.name.trim() || !draft.legal_entity.trim() || !draft.business.trim()}
          onClick={save}
        >
          {t("books.save")}
        </button>
      </div>
      </details>
      {message && <p role="status">{message}</p>}
    </section>
  );
}
