//获取当前网页可见内容的所有元素
const getVisibleContent = () =>{
    //1.定义遍历存储所有可视元素 + 视口的宽度
    const visibleElements = [];
    const viewporHeight = window.innerHeight;
    const viewporWeight = window.innerWidth;

    //2.获取页面上的所有元素，包含可见和并不可见
    const elements = document.querySelectorAll("body *");

    //3.循环遍历所有元素dom逐个处理
    for (let i = 0; i < elements.length;i++){
        //4.获取dom元素的尺寸+位置
        const element = elements[i];
        const rect = element.getBoundingClientRect();

        //5.判断元素的宽高，只要有一个为0就表示不可见
        if(rect.height === 0 || rect.width === 0)continue;

        //6.排除完全不在当前视口内的元素(上方、左侧、右侧、下方)
        if(
            rect.bottom < 0||
            rect.top > viewporHeight ||
            rect.right < 0||
            rect.left > viewporWeight
        )continue;

        //7.使用样式来判断下当前元素是否是隐藏的
        const style = window.getComputedStyle(element);
        if(
            style.display === 'none'|| //块隐藏
            style.visibility === 'hidden' || //不可见
            style.opacity == '0' //透明度
        )continue;
        //8.如果element为有意义的节点/元素，则添加进来
        if (
            element.innerText ||
            element.tagName === "IMG" ||
            element.tagName === "INPUT" ||
            element.tagName === "BUTTon"
        ) visibleElements.push(element.outerHTML);

    }

    //9.将所有的可视元素组装成字符串并添加到div标签中直接返回
    return "<div>" + visibleElements.join(" ") + "</div>"
}

const getInteractivateElements = () =>{
    //1.定义遍历存储激活元素列表 + 视频口宽高
    const interactiveElements = [];
    const viewportHeigh = window.innerHeight;
    const viewporWidth = window.innerWidth;
    //2.获取页面上所有可交互的元素，包括按钮、a标签、输入框、文本域、下拉菜单、tab等
    const elements = document.querySelectorAll('button, a, input, select,[role="button"],[tabindex]:not([tabindex="-1"])');

    //3.定义变量用于生成连续的唯一索引
    let validElementIndex = 0;
    //4.循环遍历所有元素
    for (let i = 0;i < elements.length; i++){
        //5.取出响应元素并获得尺寸+位置
        const element = elements[i];
        const rect = element.getBoundingClientRect();

        //6.宽高任意为0则跳过这条元素
        if(rect.width === 0 || rect.height === 0)continue;

        //7.视口不可见该元素则跳过
        if (
            rect.bottom < 0 ||
            rect.top > viewportHeigh ||
            rect.right < 0 ||
            rect.left > viewporWidth
        )continue;

        //8.样式不可见则跳过该元素
        const style = window.getComputedStyle(element);
        if(
            style.display === 'none' ||
            style.visibility === 'hidden' ||
            style.opacity === '0'
        )continue;

        //9.获取元素的标签并转换成小写，同时提取标签内容
        let tagName = element.tagName.toLowerCase();
        let text = '';

        //10.根据标签类型不同处理不同的逻辑，首先是输入框/文本域/下拉菜单
        if (element.value && ['input','textarea','select'].includes(tagName)){
            text = element.value;
            //11.标签为输入框则执行以下代码，记录label和placeholder
            if(tagName ==='input'){
                //12.查询输入框的label是否存在并赋值
                let labelText = '';
                if(element.id){
                    const label = document.querySelector(`label[for="${element.id}"]`);
                    if (label){
                        labelText = label.innerText.trim();
                    }
                }
                //13.查找父级或同级的label(当没有for 属性绑定时)
                if(!labelText){
                    const parentLabel = element.closest('label');
                    if(parentLabel){
                        labelText = parentLabel.innerText.trim().replace(element.value,'').trim();
                    }
                }
                //14.拼接label消息
                if (labelText){
                    text = `[Label:${labelText}]${text}`;
                }

                //15.拼接placeholder信息
                if(element.placeholder){
                    text = `${text} [Placeholder: ${element.placeholder}]`;
                }
            }

        }else if (element.innerText){
            //16.普遍元素则提取内部文本并剔除多余空格(如<button>提交</button>)
            text = element.innerText.trim().replace(/\\s+/g,'').trim()
        }else if (element.alt){
            //17.图片按钮，取alt属性
            text = element.alt;
        }else if (element.title){
            //18.取取title属性
            text = element.title;
        }else if (element.placeholder){
            //19.取placeholder属性
            text = `[Placeholder:${element.placeholder}]`;

        }else if (element.type){
            //20.兜底逻辑将元素的类型作为文本描述
            text = `[${element.type}]`;

            //21.针对没有值的Input，再次尝试获取Label和Placeholder(逻辑向上)
            if(tagName === 'input'){
                let labelText = '';
                if (element.id){
                    const label = document.querySelector(`label[for="${element.id}"]`);
                    if(label){
                        labelText = label.innerText.trim();
                    }
                }

                if(!labelText){
                    const parentLabel = element.closest('label');
                    if(parentLabel){
                        labelText = parentLabel.innerText.trim();
                    }
                }
                if (labelText){
                    text = `[label: ${labelText}] ${text}`;
                }
                if(element.placeholder){
                    text = `${text} [Placeholder: ${element.placeholder}]`;
                }
            }
        }else {
            //22.都不满足，则设置为No text
            text = `[No text]`;
        }
        //23.检测文本长度是否超过100，如果是则剔除多余部分
        if(text.length > 100){
            text = text.substring(0,97) + '...';
        }
        //24.当前元素添加data-manus-id的属性，值为manus-element-idx，这样就可以通过线索找到对应的元素
        element.setAttribute('data-manus-id', `manus-element-${validElementIndex}`);
        //25.构建css选择器
        const select = `[data-manus-id="manus-element-${validElementIndex}"]`;

        //26.将索引。标签名、文本、选择器添加到激活元素列表中
        interactiveElements.push({
            index: validElementIndex,
            tag: tagName,
            text: text,
            select: select
        });
        //27.索引自增1
        validElementIndex ++;

    }
    //28.最终返回所有激活元素数据
    return interactiveElements;
}

/**injectConsoleLogs**/

const injectConsoleLogs = () =>{
    //1.定义变量存储控制台输出日志
    window.console.logs = [];

    //2.重写window.console.log函数
    const originalLog = console.log;
    console.log = (...args) => {
        window.console.logs.push(args.join(" "));
        originalLog.apply(console,args);
    };


}