import { useEffect, useRef } from "react"
import * as d3 from "d3"

const NODE_COLORS: Record<string, string> = {
  meeting:  "#c84b31",
  person:   "#2563eb",
  task:     "#16a34a",
  deadline: "#d97706",
  decision: "#7c3aed",
}

export default function GraphView({ data }: { data: any }) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!data?.nodes || !svgRef.current) return

    const svg    = d3.select(svgRef.current)
    const width  = svgRef.current.clientWidth  || 800
    const height = svgRef.current.clientHeight || 480

    svg.selectAll("*").remove()

    const g = svg.append("g")

    // zoom
    svg.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 3])
        .on("zoom", e => g.attr("transform", e.transform))
    )

    const nodes: any[] = data.nodes.map((n: any) => ({ ...n }))
    const links: any[] = (data.links || []).map((l: any) => ({ ...l }))

    const sim = d3.forceSimulation(nodes)
      .force("link",   d3.forceLink(links).id((d: any) => d.id).distance(100))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide(30))

    const link = g.selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "#d8d0c4")
      .attr("stroke-width", 1.5)

    const node = g.selectAll("circle")
      .data(nodes)
      .join("circle")
      .attr("r", (d: any) => d.type === "meeting" ? 12 : 8)
      .attr("fill", (d: any) => NODE_COLORS[d.type] || "#8a8070")
      .attr("stroke", "#f5f2eb")
      .attr("stroke-width", 2)
      .call(
        d3.drag<SVGCircleElement, any>()
          .on("start", (event, d) => {
            if (!event.active) sim.alphaTarget(0.3).restart()
            d.fx = d.x; d.fy = d.y
          })
          .on("drag",  (event, d) => { d.fx = event.x; d.fy = event.y })
          .on("end",   (event, d) => {
            if (!event.active) sim.alphaTarget(0)
            d.fx = null; d.fy = null
          })
      )

    const label = g.selectAll("text")
      .data(nodes)
      .join("text")
      .text((d: any) => d.label || d.id)
      .attr("font-size", "10px")
      .attr("font-family", "'IBM Plex Mono', monospace")
      .attr("fill", "#0d0d0d")
      .attr("dx", 12)
      .attr("dy", 4)

    sim.on("tick", () => {
      link
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y)
      node.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y)
      label.attr("x", (d: any) => d.x).attr("y", (d: any) => d.y)
    })

    return () => { sim.stop() }
  }, [data])

  if (!data?.nodes?.length) {
    return <div className="p-6 text-sm text-muted font-mono">No graph data available.</div>
  }

  return (
    <div className="w-full h-full relative">
      {/* legend */}
      <div className="absolute top-3 right-3 flex flex-col gap-1 z-10">
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1 text-xs font-mono">
            <div className="w-3 h-3 rounded-full" style={{ background: color }} />
            {type}
          </div>
        ))}
      </div>
      <svg ref={svgRef} className="w-full h-full" />
    </div>
  )
}
