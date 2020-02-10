let timeOpts = {
    hour: 'numeric',
    minute: '2-digit',
}
let dateOpts = {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
};

function update_times(){
    let times = Array.prototype.slice.call(document.getElementsByClassName('epoch-format-time'));
    for (let e of times){
        let t = new Date(e.innerText * 1000);
        e.innerText = t.toLocaleString('default', timeOpts);
        e.classList.remove('epoch-format-time');
        e.classList.add('epoch-formatted-time');
    }

    let dates = Array.prototype.slice.call(document.getElementsByClassName('epoch-format-date'));
    for (let e of dates){
        let t = new Date(e.innerText * 1000);
        e.innerText = t.toLocaleString('default', dateOpts);
        e.classList.remove('epoch-format-date');
        e.classList.add('epoch-formatted-date');
    }
}
function make_clickable(){
    let clickables = Array.prototype.slice.call(document.getElementsByClassName('make-clickable'));
    for (let e of clickables){
        let link = e.parentElement.parentElement.parentElement;
        if (link.tagName === "A"){
            let href = e.getAttribute('data-href');
            e.onmouseenter = function() {
                link.href = href;
            }
            e.onmouseexit = function() {
                if (link.href === href) {
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
$(document).ready(function($) {
    update_elements();
});
