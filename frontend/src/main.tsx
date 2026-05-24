import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "@styles/styles.css";
import "@styles/panels.css";
import "@styles/interactive.css";
import "@styles/interactive-load.css";
import "@styles/preview-editor.css";
import "@styles/motion.css";
import "@styles/cyberpunk.css";
import "@styles/audit.css";
import "@styles/review-routing.css";
import "@styles/loaded-rows.css";
import "@styles/query-guide.css";
import "@styles/structured-sql.css";
import "@styles/workflow-action.css";
import "@styles/schema-load.css";
import "@styles/decision-workbench.css";
import "@styles/readiness-action.css";
import "@styles/action-focus.css";
import "@styles/workflow-layout.css";
import "@styles/text-safety.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
