import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import UrlInput from "./UrlInput";

describe("UrlInput", () => {
  it("disables Run until the URL is a valid issue URL", () => {
    const onRun = vi.fn();
    render(<UrlInput onRun={onRun} disabled={false} />);
    const run = screen.getByRole("button", { name: /run/i });
    expect(run).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "https://github.com/o/r/issues/7" },
    });
    expect(run).toBeEnabled();
    fireEvent.click(run);
    expect(onRun).toHaveBeenCalledWith("live", "https://github.com/o/r/issues/7");
  });

  it("Demo button triggers a replay run", () => {
    const onRun = vi.fn();
    render(<UrlInput onRun={onRun} disabled={false} />);
    fireEvent.click(screen.getByRole("button", { name: /demo/i }));
    expect(onRun).toHaveBeenCalledWith("replay", expect.any(String));
  });
});
