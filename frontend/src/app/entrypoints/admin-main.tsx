import React from "react";
import ReactDOM from "react-dom/client";
import AdminApp from "../AdminApp";
import "../../styles/index.css";
import "../../styles/apps/admin.css";
import "../../styles/shared-ui.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><AdminApp initialNav={new URLSearchParams(window.location.search).get("section") === "vocabulary" ? "Vocabulary" : "Admin Home"} /></React.StrictMode>,
);
