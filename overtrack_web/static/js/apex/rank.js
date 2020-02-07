const width = 362
const height = 133

const margin = ({top: 20, right: 30, bottom: 30, left: 40})

const fulldata = rpHistory.map((x, i) => ({ value: x, index: i + 1 }))
const data = fulldata.slice(Math.max(0, fulldata.length - 50))

const dmin = Math.min(1000, d3.min(data, d => d.value))
const dmaxfloor = d3.max(data, d => d.value)

let rankBorders = [
      0,  300,  600,  900,
    1200, 1600, 2000, 2400,
    2800, 3300, 3800, 4300,
    4800, 5400, 6000, 6600,
    7200, 7900, 8600, 9300,
    10000
]

let dmaxceil = 0
for (let i = 0; i < rankBorders.length; i++) {
    if (dmaxfloor < rankBorders[i]) {
        dmaxceil = rankBorders[i]
        break
    }
}

let dmax = dmaxfloor >= 10000 ? dmaxfloor : dmaxceil
rankBorders = rankBorders.filter(x => x >= dmin && x <= dmax)

const minimal = rankBorders.length > 5
if (minimal) {
    rankBorders = [
          0,
        1200,
        2800,
        4800,
        7200,
        10000
    ]

    for (let i = 0; i < rankBorders.length; i++) {
        if (dmaxfloor < rankBorders[i]) {
            dmaxceil = rankBorders[i]
            break
        }
    }

    dmax = dmaxfloor >= 1000 ? dmaxfloor : dmaxceil
    rankBorders = rankBorders.filter(x => x >= dmin && x <= dmax)
}

if (dmax >= 10150 && dmin < dmax) {
    rankBorders.push(dmax)
}

const rankNums = ({
      "0": "IV",
     "300": "III",
     "600": "II",
     "900": "I",
    "1200": "IV",
    "1600": "III",
    "2000": "II",
    "2400": "I",
    "2800": "IV",
    "3300": "III",
    "3800": "II",
    "4300": "I",
    "4800": "IV",
    "5400": "III",
    "6000": "II",
    "6600": "I",
    "7200": "IV",
    "7900": "III",
    "8600": "II",
    "9300": "I",
    "10000": "",
})

const rankImages = ({
      "00": "bronze",
     "300": "bronze",
     "600": "bronze",
     "900": "bronze",
    "1200": "silver",
    "1600": "silver",
    "2000": "silver",
    "2400": "silver",
    "2800": "gold",
    "3300": "gold",
    "3800": "gold",
    "4300": "gold",
    "4800": "platinum",
    "5400": "platinum",
    "6000": "platinum",
    "6600": "platinum",
    "7200": "diamond",
    "7900": "diamond",
    "8600": "diamond",
    "9300": "diamond",
    "10000": "predator",
})

const svg = d3.select("#graph-svg")

const x = d3.scaleLinear()
    .domain([data[0].index, data[data.length - 1].index])
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
    .call(g => g.selectAll(".tick").filter(t => t <= 10000).insert("image", "text")
            .attr("x", 2.6)
            .attr("y", minimal ? -13 : -15)
            .attr("width", 25)
            .attr("height", 25)
            .attr("xlink:href", t => "/static/images/apex/rank-" + rankImages[t] + ".png"))
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

