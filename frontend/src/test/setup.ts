import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
});
