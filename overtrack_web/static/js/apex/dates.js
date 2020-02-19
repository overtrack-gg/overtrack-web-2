let dateDividerOpts = {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
};
let lastText = new Date().toLocaleString('default', dateDividerOpts);

function update_dividers(){
    let dates = Array.prototype.slice.call(document.getElementsByClassName('date-divider-timestamp'));
    for (let e of dates){
        let d = new Date(+e.getAttribute('data-timestamp') * 1000);
        let text = d.toLocaleString('default', dateDividerOpts);
        if (text != lastText){
            lastText = text;
            e.innerText = text;
            e.classList.remove('date-divider-invisible');
        }
        e.classList.remove('date-divider-timestamp');
    }
}
function update_rows(){
    window.setTimeout(
        ()=>{
            update_dividers();
            update_times();
            make_clickable();
        },
        0
    );
}
$(document).ready(function($) {
    update_rows();
});
