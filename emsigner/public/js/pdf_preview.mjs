const PDF_URL =
  "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.min.js";
const PDF_INTEGRITY =
  "sha384-uLiAv4VcjM5H2Jsqzl8EajEaxPugj1CIzQaCjQ8c5//vC+elhxO5pZfXGxoLQi1W";
const WORKER_URL =
  "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.worker.min.js";
const WORKER_INTEGRITY =
  "sha384-cdzss87ZwpiG252tPQexupMwS1W1lTzzgy/UlNUHXW6h8aaJpBizRQk9j8Vj3zw9";
let libraryPromise;

export function loadPdfJs() {
  if (libraryPromise) return libraryPromise;
  libraryPromise = (async () => {
    await new Promise((resolve, reject) => {
      const script = document.createElement("script");
      const timer = setTimeout(() => {
        script.remove();
        reject(new Error("PDF preview timed out"));
      }, 15000);
      script.src = PDF_URL;
      script.integrity = PDF_INTEGRITY;
      script.crossOrigin = "anonymous";
      script.onload = () => {
        clearTimeout(timer);
        resolve();
      };
      script.onerror = () => {
        clearTimeout(timer);
        script.remove();
        reject(new Error("PDF preview is unavailable"));
      };
      document.head.appendChild(script);
    });
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 15000);
    try {
      // Verify the worker too: it receives the private PDF bytes.
      const response = await fetch(WORKER_URL, {
        integrity: WORKER_INTEGRITY,
        credentials: "omit",
        signal: abort.signal,
      });
      if (!response.ok) throw new Error("PDF preview worker is unavailable");
      const body = await response.blob();
      if (body.size > 2 * 1024 * 1024)
        throw new Error("PDF preview worker exceeds its limit");
      const worker = URL.createObjectURL(
        new Blob([body], { type: "application/javascript" })
      );
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = worker;
      // The browser owns this blob URL for the document lifetime, including BFCache restores.
      return window.pdfjsLib;
    } finally {
      clearTimeout(timer);
    }
  })().catch((error) => {
    libraryPromise = undefined;
    throw error;
  });
  return libraryPromise;
}

export async function loadPdfDocument(encoded, loadLibrary = loadPdfJs) {
  const lib = await loadLibrary();
  return lib.getDocument({ data: atob(encoded), isEvalSupported: false })
    .promise;
}

/** Own one dialog's document and serialize canvas work through close and retry. */
export function createPreviewState(setState) {
  let document,
    disposed = false,
    failed = false,
    pending = true,
    generation = 0;
  let tail = Promise.resolve();
  const refresh = () => {
    if (!disposed) setState({ busy: !document || failed || pending, failed });
  };
  refresh();
  return {
    attach(pdf) {
      if (disposed) {
        Promise.resolve(pdf.destroy()).catch(() => {});
        return false;
      }
      document = pdf;
      return true;
    },
    fail() {
      if (!disposed) {
        failed = true;
        refresh();
      }
    },
    wrap(draw) {
      return (...args) => {
        if (disposed || failed || !document) return Promise.resolve();
        const ticket = ++generation;
        pending = true;
        refresh();
        const next = tail.then(async () => {
          if (disposed || ticket !== generation) return;
          try {
            await draw(...args);
          } catch (_) {
            if (!disposed) failed = true;
          } finally {
            if (ticket === generation) pending = false;
            refresh();
          }
        });
        tail = next;
        return next;
      };
    },
    dispose() {
      disposed = true;
      ++generation;
      if (document) Promise.resolve(document.destroy()).catch(() => {});
    },
  };
}
