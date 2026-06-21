import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { fireEvent } from "@testing-library/react";
import App from "./App";

describe("App", () => {
  it("renders the Triage wordmark", () => {
    render(<App />);
    expect(screen.getByRole("banner")).toHaveTextContent("Triage");
  });
});

it("plays the replay run when Demo is clicked", async () => {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: /demo/i }));
  expect(await screen.findByText(/extracted 2 steps/i, {}, { timeout: 4000 })).toBeInTheDocument();
});
