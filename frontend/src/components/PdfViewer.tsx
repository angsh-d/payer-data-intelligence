import { useState, useEffect, useRef, useCallback } from 'react'
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from 'lucide-react'
import * as pdfjsLib from 'pdfjs-dist'

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url
).toString()

interface PdfViewerProps {
  url: string
  page?: number
  onPageChange?: (page: number) => void
}

export default function PdfViewer({ url, page = 1, onPageChange }: PdfViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [pdfDoc, setPdfDoc] = useState<pdfjsLib.PDFDocumentProxy | null>(null)
  const [currentPage, setCurrentPage] = useState(page)
  const [totalPages, setTotalPages] = useState(0)
  const [scale, setScale] = useState(1.0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const renderTaskRef = useRef<any>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)

    const loadPdf = async () => {
      try {
        const doc = await pdfjsLib.getDocument(url).promise
        setPdfDoc(doc)
        setTotalPages(doc.numPages)
        setLoading(false)
      } catch (err: any) {
        setError('Failed to load PDF')
        setLoading(false)
      }
    }

    loadPdf()

    return () => {
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel()
      }
    }
  }, [url])

  useEffect(() => {
    if (page !== currentPage && page >= 1 && page <= totalPages) {
      setCurrentPage(page)
    }
  }, [page, totalPages])

  const renderPage = useCallback(async () => {
    if (!pdfDoc || !canvasRef.current || !containerRef.current) return

    if (renderTaskRef.current) {
      renderTaskRef.current.cancel()
      renderTaskRef.current = null
    }

    try {
      const pdfPage = await pdfDoc.getPage(currentPage)
      const canvas = canvasRef.current
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      const containerWidth = containerRef.current.clientWidth - 32
      const unscaledViewport = pdfPage.getViewport({ scale: 1.0 })
      const fitScale = containerWidth / unscaledViewport.width
      const viewport = pdfPage.getViewport({ scale: fitScale * scale })

      const dpr = window.devicePixelRatio || 1
      canvas.width = viewport.width * dpr
      canvas.height = viewport.height * dpr
      canvas.style.width = `${viewport.width}px`
      canvas.style.height = `${viewport.height}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

      const renderTask = pdfPage.render({
        canvasContext: ctx,
        viewport,
        canvas,
      } as any)
      renderTaskRef.current = renderTask
      await renderTask.promise
      renderTaskRef.current = null
    } catch (err: any) {
      if (err?.name !== 'RenderingCancelledException') {
        console.error('PDF render error:', err)
      }
    }
  }, [pdfDoc, currentPage, scale])

  useEffect(() => {
    renderPage()
  }, [renderPage])

  useEffect(() => {
    if (!containerRef.current) return
    const observer = new ResizeObserver(() => renderPage())
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [renderPage])

  const goToPage = (p: number) => {
    if (p < 1 || p > totalPages) return
    setCurrentPage(p)
    onPageChange?.(p)
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-[#0071e3] border-t-transparent rounded-full animate-spin" />
          <span className="text-[13px] text-[#86868b]">Loading PDF...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="text-[13px] text-[#d70015]">{error}</span>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-4 py-2 bg-white border-b border-[rgba(0,0,0,0.06)] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-1">
          <button
            onClick={() => goToPage(currentPage - 1)}
            disabled={currentPage <= 1}
            className="p-1 rounded-md hover:bg-[rgba(0,0,0,0.04)] disabled:opacity-30 transition-colors"
          >
            <ChevronLeft className="w-4 h-4 text-[#6e6e73]" />
          </button>
          <span className="text-[12px] text-[#6e6e73] min-w-[80px] text-center">
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => goToPage(currentPage + 1)}
            disabled={currentPage >= totalPages}
            className="p-1 rounded-md hover:bg-[rgba(0,0,0,0.04)] disabled:opacity-30 transition-colors"
          >
            <ChevronRight className="w-4 h-4 text-[#6e6e73]" />
          </button>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setScale(s => Math.max(0.5, s - 0.15))}
            className="p-1 rounded-md hover:bg-[rgba(0,0,0,0.04)] transition-colors"
          >
            <ZoomOut className="w-4 h-4 text-[#6e6e73]" />
          </button>
          <span className="text-[11px] text-[#aeaeb2] min-w-[40px] text-center">
            {Math.round(scale * 100)}%
          </span>
          <button
            onClick={() => setScale(s => Math.min(3, s + 0.15))}
            className="p-1 rounded-md hover:bg-[rgba(0,0,0,0.04)] transition-colors"
          >
            <ZoomIn className="w-4 h-4 text-[#6e6e73]" />
          </button>
        </div>
      </div>
      <div
        ref={containerRef}
        className="flex-1 overflow-auto bg-[#e8e8ed] p-4 flex justify-center"
      >
        <canvas
          ref={canvasRef}
          className="shadow-lg rounded-sm"
          style={{ maxWidth: '100%' }}
        />
      </div>
    </div>
  )
}
