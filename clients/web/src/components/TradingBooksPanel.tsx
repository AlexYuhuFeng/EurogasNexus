import { useCallback, useEffect, useState } from "react";

import { api, type TradingBookInput, type TradingBooksDTO } from "@/api/client";

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

  return (
    <section className="workspace-panel span-3 trading-books-panel" aria-labelledby="trading-books-title">
      <h2 id="trading-books-title">{t("books.title")}</h2>
      {books && books.books.length === 0 && <p className="muted">{t("books.empty")}</p>}
      {books && books.books.length > 0 && (
        <table className="position-ladder" data-trading-books="true">
          <thead>
            <tr>
              <th scope="col">{t("books.legal_entity")}</th>
              <th scope="col">{t("books.region")}</th>
              <th scope="col">{t("books.business")}</th>
              <th scope="col">{t("books.book")}</th>
              <th scope="col" className="num">{t("books.contracts")}</th>
              <th scope="col" className="num">{t("books.orders")}</th>
            </tr>
          </thead>
          <tbody>
            {books.books.map((book) => (
              <tr key={book.book_id} data-record="trading-book">
                <td>{book.legal_entity}</td>
                <td>{t(`books.region_${book.region}`)}</td>
                <td>{book.business}</td>
                <td><strong>{book.name}</strong> <small>{book.book_id} · {book.base_currency}</small></td>
                <td className="num">{book.contracts}</td>
                <td className="num">{book.orders}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {books && (books.unassigned.contracts > 0 || books.unassigned.orders > 0) && (
        <p className="muted">{t("books.unassigned", books.unassigned)}</p>
      )}
      <div className="licence-form">
        <label><span>{t("books.book_id")}</span><input value={draft.book_id} onChange={field("book_id")} /></label>
        <label><span>{t("books.name")}</span><input value={draft.name} onChange={field("name")} /></label>
        <label><span>{t("books.legal_entity")}</span><input value={draft.legal_entity} onChange={field("legal_entity")} /></label>
        <label>
          <span>{t("books.region")}</span>
          <select value={draft.region} onChange={field("region")}>
            {REGIONS.map((region) => <option key={region} value={region}>{t(`books.region_${region}`)}</option>)}
          </select>
        </label>
        <label><span>{t("books.business")}</span><input value={draft.business} onChange={field("business")} /></label>
        <label><span>{t("books.base_currency")}</span><input value={draft.base_currency} onChange={field("base_currency")} maxLength={3} /></label>
        <label><span>{t("books.members")}</span><input value={draft.members} onChange={field("members")} /></label>
        <button
          type="button"
          disabled={!draft.book_id.trim() || !draft.name.trim() || !draft.legal_entity.trim() || !draft.business.trim()}
          onClick={save}
        >
          {t("books.save")}
        </button>
      </div>
      {message && <p role="status">{message}</p>}
    </section>
  );
}
