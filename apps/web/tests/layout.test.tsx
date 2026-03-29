import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import RootLayout from "../app/layout";

describe("RootLayout", () => {
  it("renders children inside html > body", () => {
    // RootLayout renders <html><body>{children}</body></html>.
    // jsdom strips the outer html/body tags (it manages those itself), so
    // we verify that our children content reaches the DOM.
    render(
      <RootLayout>
        <span data-testid="child">hello</span>
      </RootLayout>
    );
    expect(screen.getByTestId("child")).toBeInTheDocument();
    expect(screen.getByTestId("child").textContent).toBe("hello");
  });

  it("renders multiple children", () => {
    render(
      <RootLayout>
        <p data-testid="p1">first</p>
        <p data-testid="p2">second</p>
      </RootLayout>
    );
    expect(screen.getByTestId("p1")).toBeInTheDocument();
    expect(screen.getByTestId("p2")).toBeInTheDocument();
  });
});
