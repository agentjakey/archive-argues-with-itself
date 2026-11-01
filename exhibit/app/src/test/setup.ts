import "@testing-library/jest-dom/vitest";

// jsdom has no scrolling; the app scrolls to the top on every screen change.
window.scrollTo = () => undefined;
