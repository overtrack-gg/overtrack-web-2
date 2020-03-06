let timeOpts = {
    hour: 'numeric',
    minute: '2-digit',
}
let dateOpts = {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
};
let datetimeOpts = {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
};

var styleSheet = document.createElement("style");
styleSheet.type = "text/css";
document.head.appendChild(styleSheet);
let updateIteration = 0

function update_times(){
    // Prevent reflow by only revealing the format update at the end
    // On my machine this reduces update_times from ~100ms -> ~20ms for a smallish update
    styleSheet.innerText = '.epoch-format-iteration-' + (+updateIteration) + ' { display: none; }'

    let times = Array.prototype.slice.call(document.getElementsByClassName('epoch-format-time'));
    for (let e of times){
        e.classList.add('epoch-format-iteration-' + (+updateIteration));
        e.classList.remove('epoch-format-time');
        e.classList.add('epoch-formatted-time');
        let t = new Date(e.innerText * 1000);
        e.innerText = t.toLocaleString('default', timeOpts);
    }

    let dates = Array.prototype.slice.call(document.getElementsByClassName('epoch-format-date'));
    for (let e of dates){
        e.classList.add('epoch-format-iteration-' + (+updateIteration));
        e.classList.remove('epoch-format-date');
        e.classList.add('epoch-formatted-date');
        let t = new Date(e.innerText * 1000);
        e.innerText = t.toLocaleString('default', dateOpts);
    }

    let datetimes = Array.prototype.slice.call(document.getElementsByClassName('epoch-format-datetime'));
    for (let e of datetimes){
        e.classList.add('epoch-format-iteration-' + (+updateIteration));
        e.classList.remove('epoch-format-datetime');
        e.classList.add('epoch-formatted-datetime');
        let t = new Date(e.innerText * 1000);
        e.innerText = t.toLocaleString('default', datetimeOpts);
    }

    styleSheet.innerText = '';
    updateIteration += 1;
}
function make_clickable(){
    let clickables = Array.prototype.slice.call(document.getElementsByClassName('make-clickable'));
    for (let e of clickables){
        let link = e.parentElement.parentElement.parentElement;
        if (link.tagName === "A"){
            let href = e.getAttribute('data-href');
            e.onmouseenter = event => {
                link.href = href;
            }
            e.onmouseleave = event => {
                if (link.href.indexOf(href) != -1) {
                    link.removeAttribute('href')
                }
            }
        }
        e.classList.remove('make-clickable');
        e.classList.add('clickable');
    }
}
function update_elements(){
    window.setTimeout(
        ()=>{
            update_times();
            make_clickable();
        },
        0
    );
}
document.addEventListener("DOMContentLoaded", function(event) {
    update_elements();
    $('[data-toggle="tooltip"]').tooltip()
});
