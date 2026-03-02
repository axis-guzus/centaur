import { ThreadLayout } from "@/components/thread/thread-layout";

const STORAGE_KEY = "threads.sidebar.collapsed.v1";
const COLLAPSE_CLASS = "threads-sidebar-collapsed";

const SIDEBAR_BOOTSTRAP_SCRIPT = `
(() => {
  try {
    var collapsed = window.localStorage.getItem("${STORAGE_KEY}") === "1";
    document.documentElement.classList.toggle("${COLLAPSE_CLASS}", collapsed);
  } catch (_) {}
})();
`;

export default function ThreadsLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <script dangerouslySetInnerHTML={{ __html: SIDEBAR_BOOTSTRAP_SCRIPT }} />
      <ThreadLayout>{children}</ThreadLayout>
    </>
  );
}
