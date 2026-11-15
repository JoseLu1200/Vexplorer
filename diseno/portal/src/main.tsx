import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { App } from "./App";
import { RouterProvider } from "./router";
import { StoreProvider } from "./state";
import { WorkspaceProvider } from "./workspace/store";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider>
      <WorkspaceProvider>
        <StoreProvider>
          <App />
        </StoreProvider>
      </WorkspaceProvider>
    </RouterProvider>
  </StrictMode>,
);
