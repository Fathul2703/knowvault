import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AnswerMarkdown } from "@/features/chat/answer-markdown";

function renderAnswer(text: string, sources = [1, 2]) {
  const onCite = vi.fn();
  const view = render(<AnswerMarkdown text={text} sources={new Set(sources)} onCite={onCite} />);
  return { onCite, container: view.container };
}

describe("AnswerMarkdown", () => {
  it("links citations of given sources and calls back with the number", async () => {
    const { onCite } = renderAnswer("Twelve days **per year** [1]. Also [2, 3].");
    await userEvent.click(screen.getByRole("button", { name: "Show source 1" }));
    expect(onCite).toHaveBeenCalledWith(1);
    expect(screen.getByRole("button", { name: "Show source 2" })).toBeInTheDocument();
    // There is no source 3: shown as text, not as a link.
    expect(screen.queryByRole("button", { name: "Show source 3" })).toBeNull();
    expect(screen.getByText("[3]")).toBeInTheDocument();
    expect(screen.getByText("per year").tagName).toBe("STRONG");
  });

  it("never renders raw HTML from the answer", () => {
    const { container } = renderAnswer(
      'Hi <img src=x onerror="alert(1)"> <script>alert(2)</script> [click](javascript:alert(3))',
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("click")).toBeInTheDocument();
    expect(container.innerHTML).not.toContain("javascript:");
  });

  it("leaves markers inside code alone and renders lists", () => {
    const { container } = renderAnswer("- one [1]\n- two\n\n`array[1]`");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("code")?.textContent).toBe("array[1]");
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("opens external links in a new tab without opener access", () => {
    renderAnswer("[docs](https://example.com)");
    const link = screen.getByRole("link", { name: "docs" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
});
