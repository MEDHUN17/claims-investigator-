import { pdfjs } from 'react-pdf'
import workerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

// PDF.js worker bundled locally by Vite (no CDN).
pdfjs.GlobalWorkerOptions.workerSrc = workerSrc

export { pdfjs }
