import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { ThemeProvider } from "./shared/design";
// Design tokens and fonts load before the legacy stylesheet so the current app
// renders unchanged while the token layer becomes available (see tokens.css).
import "./shared/design/tokens.css";
import "./shared/design/fonts.css";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>,
);
