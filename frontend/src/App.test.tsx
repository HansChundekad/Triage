import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import App from "./App";

describe("App", () => {
  it("renders the Triage wordmark", () => {
    render(<App />);
    expect(screen.getByRole("banner")).toHaveTextContent("Triage");
  });
});
