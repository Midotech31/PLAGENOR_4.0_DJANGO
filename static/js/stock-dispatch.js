'use strict';
const stockAdd = document.getElementById('dispatch-add');
if (stockAdd) {
  stockAdd.addEventListener('click', () => {
    const total = document.getElementById('id_lines-TOTAL_FORMS');
    const count = Number(total.value);
    if (count >= 100) return;
    const section = document.createElement('div');
    section.innerHTML = document.getElementById('dispatch-empty').innerHTML.replaceAll('__prefix__', String(count));
    document.getElementById('dispatch-lines').append(...section.childNodes);
    total.value = String(count + 1);
    stockAdd.disabled = count + 1 >= 100;
  });
}
