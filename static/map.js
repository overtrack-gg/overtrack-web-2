const RES = "/static/"
const IMAGE = "/static/images/"

var locations = route.locations;
var landed_index = route.landed_location_index;
var [drop, travel] = [route.locations.slice(0, landed_index), route.locations.slice(landed_index - 1)];
// var combat = combat;

const TIMESCALE = 10;

const TIMESTART = locations[0][0];
const TIMEEND = locations[locations.length - 1][0];
const TIMEDURATION = TIMEEND - TIMESTART;

const LINE_SIZE = 2;
const ELIM_SCALE_INIT = 30;
const ELIM_SCALE = 15;

var assist_visibility = "hidden";

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
        .attr("x", -20)
        .attr("y", 0)
        .attr("width", 450)
        .attr("height", 50)
        .attr("fill", "Black")
        .attr("transform", "skewX(-40)")
        .attr("opacity", 0.5)

    overlay.append("image")
        .attr("xlink:href", IMAGE + "knock.svg")
        .attr("x", 6)
        .attr("y", 6)
        .attr("width", 16)
        .attr("height", 16)

    overlay.append("text")
        .attr("x", 28)
        .attr("y", 19)
        .attr("fill", "White")
        .attr("pointer-events", "none")
        .text("Knockdown")

    overlay.append("image")
        .attr("xlink:href", IMAGE + "elim.svg")
        .attr("x", 6)
        .attr("y", 28)
        .attr("width", 16)
        .attr("height", 16)

    overlay.append("text")
        .attr("x", 28)
        .attr("y", 41)
        .attr("fill", "White")
        .attr("pointer-events", "none")
        .text("Elimination")

    overlay.append("rect")
        .attr("x", 125+30)
        .attr("y", 10)
        .attr("width", 125)
        .attr("height", 30)
        .attr("fill", "#992e26")
        .attr("transform", "skewX(-40)")
        .attr("cursor", "pointer")
        .on("mouseover", function () {
            d3.select(this).attr("fill", "#b92e26")
        })
        .on("mouseout", function () {
            d3.select(this).attr("fill", "#992e26")
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
        })
        .on("dblclick", function() {
            d3.event.stopPropagation()
        })

    overlay.append("text")
        .attr("x", 137+10)
        .attr("y", 30)
        .attr("fill", "White")
        .attr("pointer-events", "none")
        .text("Toggle Assists")

    overlay.append("rect")
        .attr("x", 260+30)
        .attr("y", 10)
        .attr("width", 125)
        .attr("height", 30)
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
        .attr("x", 286+10)
        .attr("y", 30)
        .attr("fill", "White")
        .attr("pointer-events", "none")
        .text("Reset View")

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
        .attr("opacity", 0.5);

    var travel_path = svg.append("path")
        .attr("d", lineFunction(travel))
        .attr("stroke", "Lime")
        .attr("stroke-width", LINE_SIZE)
        .attr("fill", "none");

    /************************************************************************
    *** EVENT ICONS
    *************************************************************************/

    var knocks_a_image = defs
        .selectAll("knocks_a")
            .data(combat.knockdown_assists)
            .enter()
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
            .append("circle")
            .attr("class", "can-collide")
            .attr("cx", function (d) { return rescale_x(d.location[0]) })
            .attr("cy", function (d) { return rescale_y(d.location[1]) })
            .attr("fill", function (d, i) { return "url(#elims_image_" + i + ")" })

    var knocks_image = defs
        .selectAll("knocks")
            .data(combat.knockdowns)
            .enter()
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
            .append("circle")
            .attr("class", "can-collide")
            .attr("cx", function (d) { return rescale_x(d.location[0]) })
            .attr("cy", function (d) { return rescale_y(d.location[1]) })
            .attr("fill", function (d, i) { return "url(#knocks_image_" + i + ")" })

    /************************************************************************
    *** TOOLTIPS
    *************************************************************************/

    drop_path.append("title").text("Drop Path");
    travel_path.append("title").text("Route Taken");
    knocks_a.append("title").text("Knockdown Assist");
    elims_a.append("title").text("Elimination Assist");
    knocks.append("title").text("Knockdown");
    elims.append("title").text("Elimination");

    /************************************************************************
    *** ZOOM SETUP
    *************************************************************************/

    var zoom = d3.zoom()
        .scaleExtent([Math.min(SIZE_X, SIZE_Y) / Math.max(SIZE_X, SIZE_Y), 50])
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
            travel_path.attr("stroke-width", LINE_SIZE / ok);
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
        .call(zoom.scaleBy, (range_x > range_y ? SIZE_X : SIZE_Y) / (Math.max(range_x, range_y) + 20))
        .call(zoom.translateTo, min_x + range_x / 2, min_y + range_y / 2);

    var k = d3.zoomTransform(svg_base.node()).k;
    var ok = k;
    if (k < 5) {
        k *= 1.5;
    } else {
        k = (k - 5) / 1.5 + 5;
    }

    /************************************************************************
    *** ROUTE ANIMATIONS
    *************************************************************************/

    var drop_path_len = drop_path.node().getTotalLength();
    var travel_path_len = travel_path.node().getTotalLength();

    var drop_length_at = [];
    for (var i = 1; i < drop.length - 1; i++) {
        var path = svg.append('path')
            .attr("d", lineFunction(drop.slice(i)))
            .attr("class", "temppath")
            .attr("visibility", "hidden");
        drop_length_at.push(path.node().getTotalLength());
    };
    var travel_length_at = [];
    for (var i = 1; i < travel.length - 1; i++) {
        var path = svg.append('path')
            .attr("d", lineFunction(travel.slice(i)))
            .attr("class", "temppath")
            .attr("visibility", "hidden");
        travel_length_at.push(path.node().getTotalLength());
    };
    svg.selectAll('.temppath').remove();

    var t = d3.transition();

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

    var travel_path_trans = travel_path
        .attr("stroke-dasharray", travel_path_len)
        .attr("stroke-dashoffset", travel_path_len)
        .transition(t)
        .delay(TIMESCALE * (route.time_landed - TIMESTART))

    for (var i = 1; i < travel.length; i++) {
        travel_path_trans = travel_path_trans.transition(t)
            .duration(TIMESCALE * (travel[i][0] - travel[i-1][0]))
            .ease(d3.easeLinear)
            .attr("stroke-dashoffset", travel_length_at[i-1] || 0);
    };

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
    draw_map()
    $("#map").on("mouseover",function(){ $("body").css("overflow-y","hidden") })
    $("#map").on("mouseout",function(){ $("body").css("overflow-y","auto") })
});
