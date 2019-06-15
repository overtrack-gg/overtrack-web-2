const RES = "/static/"
const IMAGE = "https://d2igtsro72if25.cloudfront.net/1/images/"

var locations = route.locations;
var landed_index = route.landed_location_index;
var [drop, travel_full] = [route.locations.slice(0, landed_index), route.locations.slice(landed_index - 1)];
var travel = [];
// var combat = combat;
var placed = 3;

const TIMESCALE = 10;

const TIMESTART = locations[0][0];
const TIMEEND = locations[locations.length - 1][0];
const TIMEDURATION = TIMEEND - TIMESTART;

const LINE_SIZE = 2;
const ELIM_SCALE_INIT = 30;
const ELIM_SCALE = 15;

const BTN = "#992e26";
const BTN_OVER = "#b92e26";
const BTN_ACTIVE = "#228b22";
const BTN_ACTIVE_OVER = "#22bb22";

var assist_visibility = "hidden";
var heat_visibility = "hidden";

function draw_map() {
    d3.selectAll("svg").remove();

    const SIZE_X = $('#map').width();
    const SIZE_Y = $('#map').height();
    const SIZE = Math.max(SIZE_X, SIZE_Y);

    function rescale_x(n) {
        return (n * SIZE) / 1350;
    };

    function rescale_y(n) {
        return (n * SIZE) / 1350;
    };

    function get_initial_zoom() {
        var [min_x, max_x] = d3.extent(travel_full, function (d) {
            return rescale_x(d[1][0]);
        });
        var [min_y, max_y] = d3.extent(travel_full, function (d) {
            return rescale_y(d[1][1]);
        });

        var range_x = max_x - min_x;
        var range_y = max_y - min_y;
        var range_x = max_x - min_x;
        var range_y = max_y - min_y;

        return [min_x, min_y, range_x, range_y];
    }

    var svg_base = d3.select("#map")
        .append("svg")
            .attr("width", SIZE_X)
            .attr("height", SIZE_Y)

    svg_base.append("rect")
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("fill", "Black")

    var svg = svg_base.append("g");
    var overlay = svg_base.append("g");
    var defs = svg_base.append("defs");

    svg.append("image")
        .attr("xlink:href", IMAGE + "map.jpg")
        .attr("x", 0)
        .attr("y", 0)
        .attr("width", SIZE)
        .attr("height", SIZE);

    /************************************************************************
    *** OVERLAY SETUP
    *************************************************************************/

    overlay.append("rect")
        .attr("x", -40)
        .attr("y", 0)
        .attr("width", 5 + 11 + 5 + 100 + 20 + 120 + 10 + 115 + 10 + 70 + 10 + 40)
        .attr("height", 40)
        .attr("fill", "Black")
        .attr("transform", "skewX(-40)")
        .attr("opacity", 0.75)

    /* KNOCKDOWN INFO */

    overlay.append("image")
        .attr("xlink:href", IMAGE + "knock.svg")
        .attr("x", 5)
        .attr("y", 6)
        .attr("width", 11)
        .attr("height", 11)

    overlay.append("text")
        .attr("x", 5 + 11 + 5)
        .attr("y", 6 + 10)
        .attr("fill", "White")
        .attr("pointer-events", "none")
        .text("Knockdown")

    /* ELIMINATION INFO */

    overlay.append("image")
        .attr("xlink:href", IMAGE + "elim.svg")
        .attr("x", 5)
        .attr("y", 6 + 11 + 6)
        .attr("width", 11)
        .attr("height", 11)

    overlay.append("text")
        .attr("x", 5 + 11 + 5)
        .attr("y", 6 + 11 + 6 + 10)
        .attr("fill", "White")
        .attr("pointer-events", "none")
        .attr("user-select", "none")
        .text("Elimination")

    /* TOGGLE ASSISTS */

    overlay.append("rect")
        .attr("x", 5 + 11 + 5 + 100 + 20)
        .attr("y", 8)
        .attr("width", 120)
        .attr("height", 24)
        .attr("fill", assist_visibility == "hidden" ? BTN : BTN_ACTIVE)
        .attr("transform", "skewX(-40)")
        .attr("cursor", "pointer")
        .on("mouseover", function () {
            d3.select(this).attr("fill", assist_visibility == "hidden" ? BTN_OVER : BTN_ACTIVE_OVER)
        })
        .on("mouseout", function () {
            d3.select(this).attr("fill", assist_visibility == "hidden" ? BTN : BTN_ACTIVE)
        })
        .on("click", function () {
            if (assist_visibility == "hidden") {
                assist_visibility = "visible";
                knocks_a.attr("visibility", "visible")
                elims_a.attr("visibility", "visible")
            } else {
                assist_visibility = "hidden";
                knocks_a.attr("visibility", "hidden")
                elims_a.attr("visibility", "hidden")
            }
            d3.select(this).attr("fill", assist_visibility == "hidden" ? BTN_OVER : BTN_ACTIVE_OVER)
        })
        .on("dblclick", function() {
            d3.event.stopPropagation()
        })

    overlay.append("text")
        .attr("x", 5 + 11 + 5 + 100 + 15)
        .attr("y", 26)
        .attr("fill", "White")
        .attr("pointer-events", "none")
        .attr("user-select", "none")
        .text("Toggle Assists")

    /* TOGGLE HEATMAP */

    overlay.append("rect")
        .attr("x", 5 + 11 + 5 + 100 + 20 + 120 + 10)
        .attr("y", 8)
        .attr("width", 115)
        .attr("height", 24)
        .attr("fill", heat_visibility == "hidden" ? BTN : BTN_ACTIVE)
        .attr("transform", "skewX(-40)")
        .attr("cursor", "pointer")
        .on("mouseover", function () {
            d3.select(this).attr("fill", heat_visibility == "hidden" ? BTN_OVER : BTN_ACTIVE_OVER)
        })
        .on("mouseout", function () {
            d3.select(this).attr("fill", heat_visibility == "hidden" ? BTN : BTN_ACTIVE)
        })
        .on("click", function () {
            if (heat_visibility == "hidden") {
                heat_visibility = "visible";
                heatmap.attr("visibility", "visible")
                drop_path.attr("visibility", "hidden")
                d3.selectAll("travel-path").attr("visibility", "hidden");
            } else {
                heat_visibility = "hidden";
                heatmap.attr("visibility", "hidden")
                drop_path.attr("visibility", "visible")
                d3.selectAll(".travel-path").attr("visibility", "visible");
            }
            d3.select(this).attr("fill", heat_visibility == "hidden" ? BTN_OVER : BTN_ACTIVE_OVER)
        })
        .on("dblclick", function() {
            d3.event.stopPropagation()
        })

    overlay.append("text")
        .attr("x", 5 + 11 + 5 + 100 + 20 + 120 + 5)
        .attr("y", 26)
        .attr("fill", "White")
        .attr("pointer-events", "none")
        .attr("user-select", "none")
        .text("Activity Map")

    /* REPLAY */

    overlay.append("rect")
        .attr("x", 5 + 11 + 5 + 100 + 20 + 120 + 10 + 115 + 10)
        .attr("y", 8)
        .attr("width", 70)
        .attr("height", 24)
        .attr("fill", "#992e26")
        .attr("transform", "skewX(-40)")
        .attr("cursor", "pointer")
        .on("mouseover", function () {
            d3.select(this).attr("fill", "#b92e26")
        })
        .on("mouseout", function () {
            d3.select(this).attr("fill", "#992e26")
        })
        .on("click", draw_map)

    overlay.append("text")
        .attr("x", 5 + 11 + 5 + 100 + 20 + 120 + 10 + 115 + 5)
        .attr("y", 26)
        .attr("fill", "White")
        .attr("pointer-events", "none")
        .text("Replay")

    /************************************************************************
    *** ROUTE SETUP
    *************************************************************************/

    var lineFunction = d3.line()
        .x(function (d) { return rescale_x(d[1][0]); })
        .y(function (d) { return rescale_y(d[1][1]); })
        .curve(d3.curveCatmullRom.alpha(0.5));

    var drop_path = svg.append("path")
        .attr("d", lineFunction(drop))
        .attr("stroke", "Cyan")
        .attr("stroke-width", LINE_SIZE)
        .attr("fill", "none")
        .attr("opacity", 0.5)
        .attr("visibility", heat_visibility == "hidden" ? "visible" : "hidden")

    let travel_paths = [];

    for (let i = 0; i < travel.length; i++) {
        travel_paths.push(
            svg.append("path")
                .attr("d", lineFunction(travel[i].route))
                .attr("class", "travel-path")
                .attr("stroke", "Lime")
                .attr("stroke-width", LINE_SIZE)
                .attr("fill", "none")
                .attr("visibility", heat_visibility === "hidden" ? "visible" : "hidden")
        );
    }

    /************************************************************************
    *** HEATMAP SETUP
    *************************************************************************/

    defs.append("filter")
        .attr("id", "blur")
        .append("feGaussianBlur")
            .attr("in", "SourceGraphic")
            .attr("stdDeviation", 10)

    var heatmap = svg
        .append("g")
        .style("filter", "url(#blur)")
        .attr("visibility", heat_visibility)

    heatmap.append("rect")
        .attr("x", 0)
        .attr("y", 0)
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("visibility", "hidden")

    heatmap
        .selectAll("travel-heatmap")
            .data(travel_full)
            .enter()
            .append("circle")
            .attr("class", "travel-heatmap")
            .attr("cx", function (d) { return rescale_x(d[1][0]) })
            .attr("cy", function (d) { return rescale_y(d[1][1]) })
            .attr("r", 0)
            .attr("fill", "Lime")
            .attr("opacity", 0.1)

    heatmap
        .selectAll("activity-heatmap")
            .data(combat.knockdown_assists)
            .enter()
            .filter(function (d) { return "location" in d; })
            .append("circle")
            .attr("class", "activity-heatmap")
            .attr("cx", function (d) { return rescale_x(d.location[0]) })
            .attr("cy", function (d) { return rescale_y(d.location[1]) })
            .attr("r", 0)
            .attr("fill", "Red")
            .attr("opacity", 0.5)

    heatmap
        .selectAll("activity-heatmap")
            .data(combat.elimination_assists)
            .enter()
            .filter(function (d) { return "location" in d; })
            .append("circle")
            .attr("class", "activity-heatmap")
            .attr("cx", function (d) { return rescale_x(d.location[0]) })
            .attr("cy", function (d) { return rescale_y(d.location[1]) })
            .attr("r", 0)
            .attr("fill", "Red")
            .attr("opacity", 0.5)

    heatmap
        .selectAll("activity-heatmap")
            .data(combat.knockdowns)
            .enter()
            .filter(function (d) { return "location" in d; })
            .append("circle")
            .attr("class", "activity-heatmap")
            .attr("cx", function (d) { return rescale_x(d.location[0]) })
            .attr("cy", function (d) { return rescale_y(d.location[1]) })
            .attr("r", 0)
            .attr("fill", "Red")
            .attr("opacity", 0.5)

    heatmap
        .selectAll("activity-heatmap")
            .data(combat.eliminations)
            .enter()
            .filter(function (d) { return "location" in d; })
            .append("circle")
            .attr("class", "activity-heatmap")
            .attr("cx", function (d) { return rescale_x(d.location[0]) })
            .attr("cy", function (d) { return rescale_y(d.location[1]) })
            .attr("r", 0)
            .attr("fill", "Red")
            .attr("opacity", 0.5)

    if (placed > 1) {
        heatmap.selectAll("activity-heatmap")
            .append("circle")
            .attr("class", "activity-heatmap")
            .attr("cx", rescale_x(locations[locations.length - 1][1][0]))
            .attr("cy", rescale_y(locations[locations.length - 1][1][1]))
            .attr("r", 0)
            .attr("fill", "Red")
            .attr("opacity", 0.5)
    }

    /************************************************************************
    *** EVENT ICONS
    *************************************************************************/

    var knocks_a_image = defs
        .selectAll("knocks_a")
            .data(combat.knockdown_assists)
            .enter()
            .filter(function (d) { return "location" in d; })
            .append("pattern")
            .attr("id", function (d, i) { return "knocks_a_image_" + i + "" })
            .attr("width", 1)
            .attr("height", 1)
            .attr("viewBox", "0 0 100 100")
            .attr("preserveAspectRatio", "none")
                .append("image")
                .attr("xlink:href", IMAGE + "knock_assist.svg")
                .attr("width", 100)
                .attr("height", 100)
                .attr("preserveAspectRatio", "none")

    var knocks_a = svg
        .selectAll("knocks_a")
            .data(combat.knockdown_assists)
            .enter()
            .filter(function (d) { return "location" in d; })
            .append("circle")
            .attr("class", "can-collide")
            .attr("cx", function (d) { return rescale_x(d.location[0]) })
            .attr("cy", function (d) { return rescale_y(d.location[1]) })
            .attr("fill", function (d, i) { return "url(#knocks_a_image_" + i + ")" })
            .attr("visibility", assist_visibility)

    var elims_a_image = defs
        .selectAll("elims_a")
            .data(combat.elimination_assists)
            .enter()
            .filter(function (d) { return "location" in d; })
            .append("pattern")
            .attr("id", function (d, i) { return "elims_a_image_" + i + "" })
            .attr("width", 1)
            .attr("height", 1)
            .attr("viewBox", "0 0 100 100")
            .attr("preserveAspectRatio", "none")
                .append("image")
                .attr("xlink:href", IMAGE + "elim_assist.svg")
                .attr("width", 100)
                .attr("height", 100)
                .attr("preserveAspectRatio", "none")

    var elims_a = svg
        .selectAll("elims_a")
            .data(combat.elimination_assists)
            .enter()
            .filter(function (d) { return "location" in d; })
            .append("circle")
            .attr("class", "can-collide")
            .attr("cx", function (d) { return rescale_x(d.location[0]) })
            .attr("cy", function (d) { return rescale_y(d.location[1]) })
            .attr("fill", function (d, i) { return "url(#elims_a_image_" + i + ")" })
            .attr("visibility", assist_visibility)

    var elims_image = defs
        .selectAll("elims")
            .data(combat.eliminations)
            .enter()
            .filter(function (d) { return "location" in d; })
            .append("pattern")
            .attr("id", function (d, i) { return "elims_image_" + i + "" })
            .attr("width", 1)
            .attr("height", 1)
            .attr("viewBox", "0 0 100 100")
            .attr("preserveAspectRatio", "none")
                .append("image")
                .attr("xlink:href", IMAGE + "elim.svg")
                .attr("width", 100)
                .attr("height", 100)
                .attr("preserveAspectRatio", "none")

    var elims = svg
        .selectAll("elims")
            .data(combat.eliminations)
            .enter()
            .filter(function (d) { return "location" in d; })
            .append("circle")
            .attr("class", "can-collide")
            .attr("cx", function (d) { return rescale_x(d.location[0]) })
            .attr("cy", function (d) { return rescale_y(d.location[1]) })
            .attr("fill", function (d, i) { return "url(#elims_image_" + i + ")" })

    var knocks_image = defs
        .selectAll("knocks")
            .data(combat.knockdowns)
            .enter()
            .filter(function (d) { return "location" in d; })
            .append("pattern")
            .attr("id", function (d, i) { return "knocks_image_" + i + "" })
            .attr("width", 1)
            .attr("height", 1)
            .attr("viewBox", "0 0 100 100")
            .attr("preserveAspectRatio", "none")
                .append("image")
                .attr("xlink:href", IMAGE + "knock.svg")
                .attr("width", 100)
                .attr("height", 100)
                .attr("preserveAspectRatio", "none")

    var knocks = svg
        .selectAll("knocks")
            .data(combat.knockdowns)
            .enter()
            .filter(function (d) { return "location" in d; })
            .append("circle")
            .attr("class", "can-collide")
            .attr("cx", function (d) { return rescale_x(d.location[0]) })
            .attr("cy", function (d) { return rescale_y(d.location[1]) })
            .attr("fill", function (d, i) { return "url(#knocks_image_" + i + ")" })

    /************************************************************************
    *** TOOLTIPS
    *************************************************************************/

    drop_path.append("title").text("Drop Path");
    d3.selectAll(".travel-path").append("title").text("Route Taken");
    knocks_a.append("title").text("Knockdown Assist");
    elims_a.append("title").text("Elimination Assist");
    knocks.append("title").text("Knockdown");
    elims.append("title").text("Elimination");

    /************************************************************************
    *** ZOOM SETUP
    *************************************************************************/

    const min_scale = Math.min(SIZE_X, SIZE_Y) / Math.max(SIZE_X, SIZE_Y);
    const max_scale = 50;
    var zoom = d3.zoom()
        .scaleExtent([min_scale, max_scale])
        .translateExtent([[0, 0], [SIZE, SIZE]])
        .on("zoom", function () {
            var k = d3.event.transform.k;
            var ok = k;
            if (k < 5) {
                k *= 1.5;
            } else {
                k = (k - 5) / 1.5 + 5;
            }
            svg.attr("transform", d3.event.transform);
            drop_path.attr("stroke-width", LINE_SIZE / ok);
            d3.selectAll(".travel-path").attr("stroke-width", LINE_SIZE / ok);
            knocks_a.attr("r", ELIM_SCALE / k);
            elims_a.attr("r", ELIM_SCALE / k);
            knocks.attr("r", ELIM_SCALE / k);
            elims.attr("r", ELIM_SCALE / k);
        });

    svg_base.call(zoom);

    var [min_x, min_y, range_x, range_y] = get_initial_zoom();

    svg_base
        .call(zoom.scaleTo, 1)
        .call(zoom.translateTo, SIZE / 2, SIZE / 2);
    svg_base
        .call(zoom.scaleBy, Math.max(Math.min((range_x > range_y ? SIZE_X : SIZE_Y) / (Math.max(range_x, range_y) + 40), max_scale), min_scale))
        .call(zoom.translateTo, min_x + range_x / 2, min_y + range_y / 2);

    var k = d3.zoomTransform(svg_base.node()).k;
    var ok = k;
    if (k < 5) {
        k *= 1.5;
    } else {
        k = (k - 5) / 1.5 + 5;
    }

    /************************************************************************
    *** ANIMATION SETUP
    *************************************************************************/

    var t = d3.transition();

    /************************************************************************
    *** DROP ROUTE ANIMATIONS
    *************************************************************************/

    var drop_path_len = drop_path.node().getTotalLength();

    var drop_length_at = [];
    for (var i = 1; i < drop.length - 1; i++) {
        var path = svg.append('path')
            .attr("d", lineFunction(drop.slice(i)))
            .attr("class", "temppath")
            .attr("visibility", "hidden");
        drop_length_at.push(path.node().getTotalLength());
    };

    var drop_path_trans = drop_path
        .attr("stroke-dasharray", drop_path_len)
        .attr("stroke-dashoffset", drop_path_len)
        .transition(t)

    for (var i = 1; i < drop.length; i++) {
        drop_path_trans = drop_path_trans.transition(t)
            .duration(TIMESCALE * (drop[i][0] - drop[i-1][0]))
            .ease(d3.easeLinear)
            .attr("stroke-dashoffset", drop_length_at[i-1] || 0);
    };

    /************************************************************************
    *** TRAVEL ROUTE ANIMATIONS
    *************************************************************************/

    d3.selectAll(".travel-path").each(function (d, i) {
        path = d3.select(this);
        let travel_path = travel[i];
        if (travel_path.jump) {
            const travel_path_len = path.node().getTotalLength();

            let travel_length_at = [];
            for (let i = 1; i < travel_path.route.length - 1; i++) {
                const path = svg.append('path')
                    .attr("d", lineFunction(travel_path.route.slice(i)))
                    .attr("class", "temppath")
                    .attr("visibility", "hidden");
                travel_length_at.push(path.node().getTotalLength());
            }

            let travel_path_trans = path
                .attr("stroke-dasharray", travel_path_len)
                .attr("stroke-dashoffset", travel_path_len)
                .attr("stroke", "#bfb")
                .attr("opacity", 0.8)
                .transition(t)
                .delay(TIMESCALE * (travel_path.route[0][0] - TIMESTART));

            for (let i = 1; i < travel_path.route.length; i++) {
                travel_path_trans = travel_path_trans.transition(t)
                    .duration(TIMESCALE * (travel_path.route[i][0] - travel_path.route[i - 1][0]))
                    .attr("stroke-dashoffset", travel_length_at[i - 1] || 0);
            }
        } else {
            const travel_path_len = path.node().getTotalLength();

            let travel_length_at = [];
            for (let i = 1; i < travel_path.route.length - 1; i++) {
                const path = svg.append('path')
                    .attr("d", lineFunction(travel_path.route.slice(i)))
                    .attr("class", "temppath")
                    .attr("visibility", "hidden");
                travel_length_at.push(path.node().getTotalLength());
            }

            let travel_path_trans = path
                .attr("stroke-dasharray", travel_path_len)
                .attr("stroke-dashoffset", travel_path_len)
                .transition(t)
                .delay(TIMESCALE * (travel_path.route[0][0] - TIMESTART));

            for (let i = 1; i < travel_path.route.length; i++) {
                travel_path_trans = travel_path_trans.transition(t)
                    .duration(TIMESCALE * (travel_path.route[i][0] - travel_path.route[i - 1][0]))
                    .ease(d3.easeLinear)
                    .attr("stroke-dashoffset", travel_length_at[i - 1] || 0);
            }
        }
    });

    /************************************************************************
    *** ROUTE ANIMATION CLEANUP
    *************************************************************************/

    svg.selectAll('.temppath').remove();

    /************************************************************************
    *** HEATMAP ANIMATIONS
    *************************************************************************/

    heatmap.selectAll(".travel-heatmap")
        .attr("r", 0)
        .transition(t)
        .delay(function (d) { return TIMESCALE * (d[0] - TIMESTART) })
        .duration(500)
        .attr("r", 10)

    heatmap.selectAll(".activity-heatmap")
        .attr("r", 0)
        .transition(t)
        .delay(function (d) { return TIMESCALE * (d.timestamp - TIMESTART) })
        .duration(500)
        .attr("r", 10)

    /************************************************************************
    *** EVENT ICON ANIMATIONS
    *************************************************************************/

    knocks_a
        .attr("r", ELIM_SCALE_INIT / k)
        .attr("opacity", 0)
        .transition(t)
        .delay(function (d) { return TIMESCALE * (d.timestamp - TIMESTART) })
        .duration(500)
        .attr("r", ELIM_SCALE / k)
        .attr("opacity", 1);

    elims_a
        .attr("r", ELIM_SCALE_INIT / k)
        .attr("opacity", 0)
        .transition(t)
        .delay(function (d) { return TIMESCALE * (d.timestamp - TIMESTART) })
        .duration(500)
        .attr("r", ELIM_SCALE / k)
        .attr("opacity", 1);

    knocks
        .attr("r", ELIM_SCALE_INIT / k)
        .attr("opacity", 0)
        .transition(t)
        .delay(function (d) { return TIMESCALE * (d.timestamp - TIMESTART) })
        .duration(500)
        .attr("r", ELIM_SCALE / k)
        .attr("opacity", 1);

    elims
        .attr("r", ELIM_SCALE_INIT / k)
        .attr("opacity", 0)
        .transition(t)
        .delay(function (d) { return TIMESCALE * (d.timestamp - TIMESTART) })
        .duration(500)
        .attr("r", ELIM_SCALE / k)
        .attr("opacity", 1);
}

$(window).resize(draw_map);
$(document).ready(function () {
    let travel_last = travel_full[0];
    let travel_current = [travel_last];

    for (let i = 0; i < travel_full.length; i++) {
        let travel_next = travel_full[i];
        if (travel_last[0] + 40 < travel_next[0]) {
            travel.push({route: travel_current, jump: false});
            travel.push({route: [travel_last, travel_next], jump: true});
            travel_current = [travel_next];
        } else {
            travel_current.push(travel_next);
        }
        travel_last = travel_next;
    }
    if (travel_current.length > 1) {
        travel.push({route: travel_current, jump: false});
    }

    draw_map()
    $("#map").on("mousewheel", function(e) {
        e.preventDefault();
        e.stopPropagation();
        return false;
    })
});
