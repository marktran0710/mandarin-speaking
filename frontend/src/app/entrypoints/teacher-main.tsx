import React from "react";
import ReactDOM from "react-dom/client";
import TeacherApp from "../TeacherApp.tsx";
import "../../styles/index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <TeacherApp />
  </React.StrictMode>,
);
