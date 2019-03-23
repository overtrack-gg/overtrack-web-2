var locations = route.locations;
var landed_index = route.landed_location_index;
var [drop, travel] = [route.locations.slice(0, landed_index), route.locations.slice(landed_index)];
var eliminations = combat;


function draw_map() {
    d3.selectAll("svg").remove();
    // d3.selectAll("rect").remove();
    // d3.selectAll("g").remove();
    // d3.selectAll("image").remove();
    // d3.selectAll("path").remove();
    // d3.selectAll("circle").remove();
    // d3.selectAll("elims").remove();

    const SIZE_X = $('#map').width();
    const SIZE_Y = $('#map').height();
    const SIZE = Math.max(SIZE_X, SIZE_Y);
    const Y_OFFSET = 0;
    const X_OFFSET = 0;
    /*
    small: 1210, 1209 : 63, 57
    large: 1260, 1256 : 13, 7
    */
    const TIMESCALE = 3;

    const TIMESTART = locations[0][0];
    const TIMEEND = locations[locations.length - 1][0];
    const TIMEDURATION = TIMEEND - TIMESTART;

    const LINE_SIZE = 2;
    const LANDING_SCALE_INIT = 15;
    const LANDING_SCALE = 5;
    const ELIM_SCALE_INIT = 15;
    const ELIM_SCALE = 6;

    function rescale_x(n) {
        n -= X_OFFSET;
        return (n * SIZE) / 1350;
    };

    function rescale_y(n) {
        n -= Y_OFFSET;
        return (n * SIZE) / 1350;
    };

    // function rescale_x(n) {
    //     var base = (n - 63) * (1260 / 1210) + 13;
    //     return (base * SIZE) / 1350;
    // };

    // function rescale_y(n) {
    //     var base = (n - 57) * (1256 / 1209) + 7;
    //     return (base * SIZE) / 1350;
    // };

    function get_initial_zoom() {
        var [min_x, max_x] = d3.extent(travel, function (d) {
            return rescale_x(d[1][0]);
        });
        var [min_y, max_y] = d3.extent(travel, function (d) {
            return rescale_y(d[1][1]);
        });

        var range_x = max_x - min_x;
        var range_y = max_y - min_y;
        var range_x = max_x - min_x;
        var range_y = max_y - min_y;

        return [min_x, min_y, range_x, range_y];
    }

    var zoom = d3.zoom()
        .scaleExtent([Math.min(SIZE_X, SIZE_Y) / Math.max(SIZE_X, SIZE_Y), 50])
        .translateExtent([[0, 0], [SIZE, SIZE]])
        .on("zoom", function () {
            svg.attr("transform", d3.event.transform);
            // landing.attr("r", LANDING_SCALE / d3.event.transform.k);
            drop_path.attr("stroke-width", LINE_SIZE / d3.event.transform.k);
            travel_path.attr("stroke-width", LINE_SIZE / d3.event.transform.k);
            knocks_a.attr("r", ELIM_SCALE / d3.event.transform.k);
            knocks_a.attr("stroke-width", 1 / d3.event.transform.k);
            elims_a.attr("r", ELIM_SCALE / d3.event.transform.k);
            elims_a.attr("stroke-width", 1 / d3.event.transform.k);
            knocks.attr("r", ELIM_SCALE / d3.event.transform.k);
            knocks.attr("stroke-width", 1 / d3.event.transform.k);
            elims.attr("r", ELIM_SCALE / d3.event.transform.k);
            elims.attr("stroke-width", 1 / d3.event.transform.k);
        });

    var svg_base = d3.select("#map")
        .append("svg")
            .attr("width", SIZE_X)
            .attr("height", SIZE_Y)
            .call(zoom)

    svg_base.append("rect")
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("fill", "Black")

    var svg = svg_base.append("g");

    svg.append("image")
        .attr("xlink:href", "/static/images/map.jpg")
        .attr("x", 0)
        .attr("y", 0)
        .attr("width", SIZE)
        .attr("height", SIZE);

    var lineFunction = d3.line()
        .x(function (d) { return rescale_x(d[1][0]); })
        .y(function (d) { return rescale_y(d[1][1]); })
        .curve(d3.curveCatmullRom.alpha(0.5));

    var drop_path = svg.append("path")
        .attr("d", lineFunction(drop))
        .attr("stroke", "Cyan")
        .attr("stroke-width", LINE_SIZE)
        .attr("fill", "none")
        .attr("opacity", 0.5);

    var travel_path = svg.append("path")
        .attr("d", lineFunction(travel))
        .attr("stroke", "Lime")
        .attr("stroke-width", LINE_SIZE)
        .attr("fill", "none");

    // var landing = svg.append("circle")
    //     .attr("cx", rescale_x(locations[0][1][0]))
    //     .attr("cy", rescale_y(locations[0][1][1]))
    //     .attr("fill", "Cyan")
        // .attr("opacity", 0.75);

    var knocks_a = svg
        .selectAll("knocks_a")
            .data(eliminations.knockdown_assists)
            .enter()
            .append("circle")
            .attr("cx", function (d) { return rescale_x(d.location[0]) })
            .attr("cy", function (d) { return rescale_y(d.location[1]) })
            .attr("fill", "DarkGreen")
            .attr("stroke", "Black");

    var elims_a = svg
        .selectAll("elims_a")
            .data(eliminations.elimination_assists)
            .enter()
            .append("circle")
            .attr("cx", function (d) { return rescale_x(d.location[0]) })
            .attr("cy", function (d) { return rescale_y(d.location[1]) })
            .attr("fill", "LightGreen")
            .attr("stroke", "Black");

    var knocks = svg
        .selectAll("knocks")
            .data(eliminations.knockdowns)
            .enter()
            .append("circle")
            .attr("cx", function (d) { return rescale_x(d.location[0]) })
            .attr("cy", function (d) { return rescale_y(d.location[1]) })
            .attr("fill", "GoldenRod")
            .attr("stroke", "Black");

    var elims = svg
        .selectAll("elims")
            .data(eliminations.eliminations)
            .enter()
            .append("circle")
            .attr("cx", function (d) { return rescale_x(d.location[0]) })
            .attr("cy", function (d) { return rescale_y(d.location[1]) })
            .attr("fill", "Red")
            .attr("stroke", "Black");

    drop_path.append("title").text("Drop Path");
    travel_path.append("title").text("Route Taken");
    knocks_a.append("title").text("Knockdown Assist");
    elims_a.append("title").text("Elimination Assist");
    knocks.append("title").text("Knockdown");
    elims.append("title").text("Elimination");

    var [min_x, min_y, range_x, range_y] = get_initial_zoom();

    svg_base
        .call(zoom.scaleTo, 1)
        .call(zoom.translateTo, SIZE / 2, SIZE / 2);
    svg_base
        .call(zoom.scaleBy, (range_x > range_y ? SIZE_X : SIZE_Y) / (Math.max(range_x, range_y) + 20))
        .call(zoom.translateTo, min_x + range_x / 2, min_y + range_y / 2);

    k = d3.zoomTransform(svg_base.node()).k;

    var drop_path_len = drop_path.node().getTotalLength();
    var travel_path_len = travel_path.node().getTotalLength();

    travel_path
        .attr("stroke-dasharray", travel_path_len)
        .attr("stroke-dashoffset", travel_path_len)

    t = d3.transition();

    drop_path
        .attr("stroke-dasharray", drop_path_len)
        .attr("stroke-dashoffset", drop_path_len)
        .transition(t)
        .duration(TIMESCALE * route.time_landed)
        .ease(d3.easeLinear)
        .attr("stroke-dashoffset", 0)

    travel_path
        .transition(t)
        .delay(TIMESCALE * route.time_landed)
        .duration(TIMESCALE * (TIMEDURATION - route.time_landed))
        .ease(d3.easeLinear)
        .attr("stroke-dashoffset", 0)

    // landing
    //     .attr("r", LANDING_SCALE_INIT / k)
    //     .transition()
    //     .duration(1000)
    //     .attr("r", LANDING_SCALE / k);

    knocks_a
        .attr("r", ELIM_SCALE_INIT / k)
        .attr("opacity", 0)
        .transition(t)
        .delay(function (d) { return TIMESCALE * (d.timestamp - TIMESTART) - 250 })
        .duration(500)
        .attr("r", ELIM_SCALE / k)
        .attr("opacity", 1);

    elims_a
        .attr("r", ELIM_SCALE_INIT / k)
        .attr("opacity", 0)
        .transition(t)
        .delay(function (d) { return TIMESCALE * (d.timestamp - TIMESTART) - 250 })
        .duration(500)
        .attr("r", ELIM_SCALE / k)
        .attr("opacity", 1);

    knocks
        .attr("r", ELIM_SCALE_INIT / k)
        .attr("opacity", 0)
        .transition(t)
        .delay(function (d) { return TIMESCALE * (d.timestamp - TIMESTART) - 250 })
        .duration(500)
        .attr("r", ELIM_SCALE / k)
        .attr("opacity", 1);

    elims
        .attr("r", ELIM_SCALE_INIT / k)
        .attr("opacity", 0)
        .transition(t)
        .delay(function (d) { return TIMESCALE * (d.timestamp - TIMESTART) - 250 })
        .duration(500)
        .attr("r", ELIM_SCALE / k)
        .attr("opacity", 1);
}

$(window).resize(draw_map);
$(document).ready(draw_map);
