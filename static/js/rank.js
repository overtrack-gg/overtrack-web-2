const width = 362
const height = 133

const margin = ({top: 20, right: 30, bottom: 30, left: 40})

const fulldata = rpHistory.map((x, i) => ({ value: x, index: i + 1 }))
const data = fulldata.slice(Math.max(0, fulldata.length - 50))

const dmax = d3.max(data, d => d.value)
const dmin = d3.min(data, d => d.value)

function get_shift(x) {
    if (x < 120) return 30
    else if (x < 280) return 40
    else if (x < 480) return 50
    else if (x < 720) return 60
    else if (x < 1000) return 70
    else return 100
}
const dminshift = dmin - get_shift(dmin)
const dmaxshift = dmax + get_shift(dmax)

var rankBorders = [
      0,  30,  60,  90,
    120, 160, 200, 240,
    280, 330, 380, 430,
    480, 540, 600, 660,
    720, 790, 860, 930,
    1000
].filter(x => x >= dmin && x <= dmaxshift)

const minimal = rankBorders.length > 5

if (minimal) {
    rankBorders = [
          0,
        120,
        280,
        480,
        720,
        1000
    ].filter(x => x >= dmin && x <= dmaxshift)
}

const rankNums = ({
      "0": "IV",
     "30": "III",
     "60": "II",
     "90": "I",
    "120": "IV",
    "160": "III",
    "200": "II",
    "240": "I",
    "280": "IV",
    "330": "III",
    "380": "II",
    "430": "I",
    "480": "IV",
    "540": "III",
    "600": "II",
    "660": "I",
    "720": "IV",
    "790": "III",
    "860": "II",
    "930": "I",
    "1000": "",
})

const rankImages = ({
      "0": "bronze",
     "30": "bronze",
     "60": "bronze",
     "90": "bronze",
    "120": "silver",
    "160": "silver",
    "200": "silver",
    "240": "silver",
    "280": "gold",
    "330": "gold",
    "380": "gold",
    "430": "gold",
    "480": "platinum",
    "540": "platinum",
    "600": "platinum",
    "660": "platinum",
    "720": "diamond",
    "790": "diamond",
    "860": "diamond",
    "930": "diamond",
    "1000": "predator",
})

const svg = d3.select("#graph-svg")

const x = d3.scaleLinear()
    .domain([data[0].index, data[data.length - 1].index]).nice()
    .range([margin.left, width - margin.right])

const y = d3.scaleLinear()
    .domain([dmin, dmax]).nice()
    .range([height - margin.bottom, margin.top]);

const xAxis = g => g
    .attr("transform", `translate(0,${height - margin.bottom})`)
    .attr("color", "#ffffff")
    .call(d3.axisBottom(x).ticks(Math.min(5, data[data.length - 1].index - data[0].index)).tickSizeOuter(0))

const yAxis = g => g
    .attr("transform", `translate(${margin.left},0)`)
    .attr("color", "#ffffff")
    .call(d3.axisLeft(y).tickValues(rankBorders))

const yAxis2 = g => g
    .attr("transform", `translate(${width - margin.right},0)`)
    .attr("color", "#ffffff")
    .call(d3.axisRight(y).tickValues(rankBorders).tickSizeInner(-width + margin.left + margin.right))
    .call(g => g.selectAll(".tick").insert("image", "text")
            .attr("x", 2.6)
            .attr("y", minimal ? -13 : -15)
            .attr("width", 25)
            .attr("height", 25)
            .attr("xlink:href", t => "../static/images/rank-" + rankImages[t] + ".png"))
    .call(g => g.selectAll(".tick text")
        .text(t => minimal ? "" : rankNums[t])
        .attr("x", 15)
        .attr("y", 7)
        .attr("text-anchor", "middle")
        .attr("font-family", "Russo One"))
    .call(g => g.selectAll(".tick line")
        .attr("fill", "#959595")
        .style("opacity", 0.25))

const line = d3.line()
    .x(d => x(d.index))
    .y(d => y(d.value))

svg.append("g")
    .call(xAxis)

svg.append("path")
    .datum(data)
    .attr("fill", "none")
    .attr("stroke", "#d33")
    .attr("stroke-width", 2)
    .attr("stroke-linejoin", "round")
    .attr("stroke-linecap", "round")
    .attr("d", line)

svg.append("g")
    .call(yAxis)

svg.append("g")
    .call(yAxis2)

