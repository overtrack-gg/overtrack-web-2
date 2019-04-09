function placefreq() {
    d3.selectAll("#placefreq-svg").remove();

    const width = $('#placefreq').width();
    const height = $('#placefreq').height();

    const margin = ({top: 20, right: 20, bottom: 30, left: 40});

    var svg = d3.select("#placefreq")
        .append("svg")
            .attr("id", "placefreq-svg")
            .attr("width", width)
            .attr("height", height);

    const x = d3.scaleLinear()
        .domain([1, 20]).nice()
        .range([margin.left, width - margin.right]);

    const y = d3.scaleLinear()
        .domain([0, Math.max(...placements_data)]).nice()
        .range([height - margin.bottom, margin.top]);

    function xAxis(g) {
        g.attr("transform", `translate(${-(x(1) - x(0)) / 2}, ${height - margin.bottom})`)
            .call(d3.axisBottom(x)
                .tickSizeOuter(0)
                .tickValues([1, 3, 5, 7, 9, 11, 13, 15, 17, 19])
            )
            .call(function (g) {
                g.append("text")
                    .attr("x", width - margin.right)
                    .attr("y", -4)
                    .attr("fill", "#fff")
                    .attr("font-weight", "bold")
                    .attr("text-anchor", "end")
                    .text("Squad Placed")
            })
            .call(g => g.select(".domain").remove())
    }

    function yAxis(g) {
        g.attr("transform", `translate(${margin.left},0)`)
            .call(
                d3.axisLeft(y)
            )
            .call(function (g) {
                g.select(".domain").remove()
            })
            .call(function (g) {
                g.select(".tick:last-of-type text").clone()
                    .attr("x", 4)
                    .attr("text-anchor", "start")
                    .attr("font-weight", "bold")
                    .text("Count")
            })
    }

    bar = svg.append("g")
       .selectAll("rect")
       .data(placements_data)
       .join("rect")
       .attr("fill", function (d, i) {
           if (i === 0)
               return "#ffdf00";
           if (i === 1)
               return "#ef20ff";
           if (i === 2)
               return "#4d95ff";
           return "firebrick";
       })
       .attr("x", function (d, i) { return x(i) + 1 })
       .attr("width", function (d, i) { return Math.max(0, x(i + 1) - x(i) - 1) })
       .attr("y", function (d) { return y(d) })
       .attr("height", function (d) { return y(0) - y(d) })
       .append("title").text((d, i) => 'Placed #' + (i + 1) + ' ' + d + ' times');

    svg.append("g")
        .call(yAxis);

    svg.append("g")
        .call(xAxis);

}

function placeprob() {
    d3.selectAll("#placeprob-svg").remove();

    const width = $('#placeprob').width();
    const height = $('#placeprob').height();

    const margin = ({top: 20, right: 20, bottom: 30, left: 40});

    var svg = d3.select("#placeprob")
        .append("svg")
            .attr("id", "placeprob-svg")
            .attr("width", width)
            .attr("height", height);

    const x = d3.scaleLinear()
        .domain([1, 20]).nice()
        .range([margin.left, width - margin.right]);

    const y = d3.scaleLinear()
        .domain([0, 100]).nice()
        .range([height - margin.bottom, margin.top]);


    let linefunction1 = d3.line()
        .x((d, i) => x(i+0) + 1)
        .y((d, i) => y(d))
        .curve(d3.curveStepBefore);

    let linefunction2 = d3.line()
        .x((d, i) => x(i+1) + 1)
        .y((d, i) => y(d))
        .curve(d3.curveStepBefore);

    let linefunction3 = d3.line()
        .x((d, i) => x(i+2) + 1)
        .y((d, i) => y(d))
        .curve(d3.curveStepBefore);

    let linefunction = d3.line()
        .x((d, i) => x(i+3) + 1)
        .y((d, i) => y(d))
        .curve(d3.curveStepBefore);

    function xAxis(g) {
        g.attr("transform", `translate(0,${height - margin.bottom})`)
            .call(d3.axisBottom(x)
                .tickSizeOuter(0)
                .tickValues([1, 3, 5, 7, 9, 11, 13, 15, 17, 19])
            ).call(function (g) {
                g.append("text")
                    .attr("x", width - margin.right)
                    .attr("y", -4)
                    .attr("fill", "#fff")
                    .attr("font-weight", "bold")
                    .attr("text-anchor", "end")
                    .text("Squad Placed At Least")
            })
    }

    function yAxis(g) {
        g.attr("transform", `translate(${margin.left},0)`)
            .call(
                d3.axisLeft(y)
                .tickSizeInner(x(0) - x(20))
            )
            .call(function (g) {
                g.select(".domain").remove()
            })
            .call(function (g) {
                g.selectAll(".tick line").attr("stroke", "gray")
            })
            .call(function (g) {
                g.select(".tick:last-of-type text").clone()
                    .attr("x", 4)
                    .attr("text-anchor", "start")
                    .attr("font-weight", "bold")
                    .text("% of Time")
            })
    }

    svg.append("g")
        .call(yAxis);

    let g = svg.append("g");

    g.append("path")
        .attr("d", linefunction1(placements_prob.slice(0, 2)))
        .attr("stroke", "#ffdf00")
        .attr("stroke-width", "2")
        .attr("fill", "none");

    g.append("path")
        .attr("d", linefunction2(placements_prob.slice(1, 3)))
        .attr("stroke", "#ef20ff")
        .attr("stroke-width", "2")
        .attr("fill", "none");

    g.append("path")
        .attr("d", linefunction3(placements_prob.slice(2, 4)))
        .attr("stroke", "#4d95ff")
        .attr("stroke-width", "2")
        .attr("fill", "none");

    g.append("path")
        .attr("d", linefunction(placements_prob.slice(3)))
        .attr("stroke", "firebrick")
        .attr("stroke-width", "2")
        .attr("fill", "none");

    bar = svg.append("g")
        .selectAll("rect")
        .data(placements_prob.slice(1))
        .join("rect")
        .attr("opacity", 0)
        .attr("x", (d, i) => x(i) + 1)
        .attr("width", (d, i) => Math.max(0, x(i + 1) - x(i) - 1))
        .attr("y", y(100))
        .attr("height", y(0) - y(100))
        .append("title").text((d, i) => `${Math.round(d)}% chance of placing #${i + 1} or better`);

    svg.append("g")
        .call(xAxis);
}

placefreq();
placeprob();

$(window).resize(placefreq);
$(window).resize(placeprob);
