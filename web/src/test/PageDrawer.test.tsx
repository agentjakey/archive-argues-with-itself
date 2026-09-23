import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PageDrawer } from "../components/PageDrawer";
import type { EvidenceRow } from "../types";

function row(overrides: Partial<EvidenceRow> = {}): EvidenceRow {
  return {
    passage_id: "micro_IA1#4:0", item_id: "micro_IA1", title: "Report", year: 2001, decade: "2000s",
    jurisdiction: "federal", doc_type: "annual_report", leaf_index: 4, printed_page: "24",
    deep_link: "https://archive.org/details/micro_IA1/page/n4",
    page_thumb: "/pages/micro_IA1/n4_thumb.jpg", page_image: "/pages/micro_IA1/n4_medium.jpg",
    embed_url: "https://archive.org/embed/micro_IA1#page/n4", snippet: "s", bm25_rank: 1, dense_rank: null,
    cited: false, in_prompt: true, section_class: "body", later_years: null, offline: true,
    ...overrides,
  };
}

const ARCHIVE_IMG = "https://archive.org/download/micro_IA1/page/n4_medium.jpg";

describe("PageDrawer offline degradation (R1, both scopes)", () => {
  it("in the pack: shows the local scanned page image", () => {
    render(<PageDrawer row={row({ offline: true })} onClose={vi.fn()} offline />);
    expect(screen.getByRole("img", { name: /Page image/ })).toHaveAttribute("src", "/pages/micro_IA1/n4_medium.jpg");
    expect(screen.getByText(/Showing the scanned page from the local archive/)).toBeInTheDocument();
  });

  it("offline + not in the pack: no live image or viewer, a clear state, and the deep link", () => {
    render(<PageDrawer row={row({ offline: false, page_image: ARCHIVE_IMG })} onClose={vi.fn()} offline />);
    expect(screen.queryByRole("img")).toBeNull();                       // no <img> -> never a broken image or live fetch
    expect(screen.queryByTitle("archive.org page viewer")).toBeNull();  // no iframe fetch either
    expect(screen.getByText(/not on this device/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open on archive.org/ })).toHaveAttribute(
      "href", "https://archive.org/details/micro_IA1/page/n4");
  });

  it("online + not in the pack: keeps the archive.org image and viewer (web experience preserved)", () => {
    render(<PageDrawer row={row({ offline: false, page_image: ARCHIVE_IMG })} onClose={vi.fn()} offline={false} />);
    expect(screen.getByRole("img", { name: /Page image/ })).toHaveAttribute("src", ARCHIVE_IMG);
    expect(screen.getByTitle("archive.org page viewer")).toBeInTheDocument();
  });
});
