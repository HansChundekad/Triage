import { describe, it, expect } from "vitest";
import { isGithubIssueUrl } from "./api";

describe("isGithubIssueUrl", () => {
  it("accepts a real issue URL", () => {
    expect(isGithubIssueUrl("https://github.com/owner/repo/issues/42")).toBe(true);
  });
  it("rejects non-issue URLs", () => {
    expect(isGithubIssueUrl("https://github.com/owner/repo")).toBe(false);
    expect(isGithubIssueUrl("https://example.com/issues/1")).toBe(false);
    expect(isGithubIssueUrl("not a url")).toBe(false);
  });
});
