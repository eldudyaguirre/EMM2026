(function ($) {
    "use strict";
	
	var $window = $(window); 
	var $body = $('body'); 

	/* Preloader Effect */
	$window.on('load', function(){
		$(".preloader").fadeOut(600);
	});

	/* Sticky Header */	
	if($('.active-sticky-header').length){
		$window.on('resize', function(){
			setHeaderHeight();
		});

		function setHeaderHeight(){
	 		$("header.active-sticky-header").css("height", $('header.active-sticky-header .header-sticky').outerHeight());
		}	
	
		$window.on("scroll", function() {
			var fromTop = $(window).scrollTop();
			setHeaderHeight();
			var headerHeight = $('header.active-sticky-header .header-sticky').outerHeight()
			$("header.active-sticky-header .header-sticky").toggleClass("hide", (fromTop > headerHeight + 100));
			$("header.active-sticky-header .header-sticky").toggleClass("active", (fromTop > 600));
		});
	}	
	
	/* Slick Menu JS */
	$('#menu').slicknav({
		label : '',
		prependTo : '.responsive-menu'
	});

	if($("a[href='#top']").length){
		$(document).on("click", "a[href='#top']", function() {
			$("html, body").animate({ scrollTop: 0 }, "slow");
			return false;
		});
	}

	/* Interactive Process Layout Start */
	var element = $('.interactive');
    if (element.hasClass('interactive-process-layout')) {                
		var items = element.find('.interactive-inner-process');
		if (items.length) {
			items.on({
				mouseenter: function() {
					var index = $(this).data('index'),
						targetImg = element.find(`.interactive-process-image.img-${index}`);
		
					if($(this).hasClass('activate')) return;

					items.removeClass('activate');
					$(this).addClass('activate');

					element.find('.interactive-process-image').removeClass('show');
					targetImg.addClass('show');
				},
				mouseleave: function() {
					//stuff to do on mouse leave
				}
			});
		}                 
	}
	/* Interactive Process Layout End */

	

	

	

	

	
	
	

	

	

	

	/* Image Reveal Animation */
	if ($('.reveal').length) {
        gsap.registerPlugin(ScrollTrigger);
        let revealContainers = document.querySelectorAll(".reveal");
        revealContainers.forEach((container) => {
            let image = container.querySelector("img");
            let tl = gsap.timeline({
                scrollTrigger: {
                    trigger: container,
                    toggleActions: "play none none none"
                }
            });
            tl.set(container, {
                autoAlpha: 1
            });
            tl.from(container, 1, {
                xPercent: -100,
                ease: Power2.out
            });
            tl.from(image, 1, {
                xPercent: 100,
                scale: 1,
                delay: -1,
                ease: Power2.out
            });
        });
    }

	/* Text Effect Animation */
	function initHeadingAnimation() {
		
		if($('.text-effect').length) {
			var textheading = $(".text-effect");

			if(textheading.length === 0) return; gsap.registerPlugin(SplitText); textheading.each(function(index, el) {
				
				el.split = new SplitText(el, { 
					type: "lines,words,chars",
					linesClass: "split-line"
				});
				
				if( $(el).hasClass('text-effect') ){
					gsap.set(el.split.chars, {
						opacity: .3,
						x: "-7",
					});
				}
				el.anim = gsap.to(el.split.chars, {
					scrollTrigger: {
						trigger: el,
						start: "top 92%",
						end: "top 60%",
						markers: false,
						scrub: 1,
					},

					x: "0",
					y: "0",
					opacity: 1,
					duration: .7,
					stagger: 0.2,
				});
				
			});
		}
		
		if ($('.text-anime-style-1').length) {
			let staggerAmount 	= 0.05,
				translateXValue = 0,
				delayValue 		= 0.5,
			   animatedTextElements = document.querySelectorAll('.text-anime-style-1');
			
			animatedTextElements.forEach((element) => {
				let animationSplitText = new SplitText(element, { type: "chars, words" });
					gsap.from(animationSplitText.words, {
						duration: 1,
						delay: delayValue,
						x: 20,
						autoAlpha: 0,
						stagger: staggerAmount,
						scrollTrigger: { trigger: element, start: "top 85%" },
					});
			});		
		}
		
		if ($('.text-anime-style-2').length) {				
			let	 staggerAmount 		= 0.03,
				 translateXValue	= 20,
				 delayValue 		= 0.1,
				 easeType 			= "power2.out",
				 animatedTextElements = document.querySelectorAll('.text-anime-style-2');
			
			animatedTextElements.forEach((element) => {
				let animationSplitText = new SplitText(element, { type: "chars, words" });
					gsap.from(animationSplitText.chars, {
						duration: 1,
						delay: delayValue,
						x: translateXValue,
						autoAlpha: 0,
						stagger: staggerAmount,
						ease: easeType,
						scrollTrigger: { trigger: element, start: "top 85%"},
					});
			});		
		}
		
		if ($('.text-anime-style-3').length) {		
			let	animatedTextElements = document.querySelectorAll('.text-anime-style-3');
			
			 animatedTextElements.forEach((element) => {
				//Reset if needed
				if (element.animation) {
					element.animation.progress(1).kill();
					element.split.revert();
				}

				element.split = new SplitText(element, {
					type: "lines,words,chars",
					linesClass: "split-line",
				});
				gsap.set(element, { perspective: 400 });

				gsap.set(element.split.chars, {
					opacity: 0,
					x: "50",
				});

				element.animation = gsap.to(element.split.chars, {
					scrollTrigger: { trigger: element,	start: "top 90%" },
					x: "0",
					y: "0",
					rotateX: "0",
					opacity: 1,
					duration: 1,
					ease: Back.easeOut,
					stagger: 0.02,
				});
			});		
		}
	}
	
	if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(() => {
            initHeadingAnimation();
        });
    } else {
        window.addEventListener("load", initHeadingAnimation);
    }

	/* Parallaxie js */
	var $parallaxie = $('.parallaxie');
	if($parallaxie.length && ($window.width() > 1024))
	{
		if ($window.width() > 768) {
			$parallaxie.parallaxie({
				speed: 0.55,
				offset: 0,
			});
		}
	}

	

	

	/* What We Item List Start */
	var $what_we_item_list = $('.what-we-item-list');
	if ($what_we_item_list.length) {
		var $what_we_item = $what_we_item_list.find('.what-we-item');

		if ($what_we_item.length) {
			$what_we_item.on({
				mouseenter: function () {
					if (!$(this).hasClass('active')) {
						$what_we_item.removeClass('active'); 
						$(this).addClass('active'); 
					}
				},
				mouseleave: function () {
					// Optional: Add logic for mouse leave if needed
				}
			});
		}
	}
	/* What We Item List End */
	
})(jQuery);


function editarCancion(id){

    let editor =
    document.getElementById(
        "cancion"+id
    );

    editor.contentEditable=true;

    editor.focus();

}

function guardarCancion(id){

    let letra =
    document.getElementById(
        "cancion"+id
    ).innerText;

    fetch(
    "/guardar-cancion/"+id+"/",
    {

        method:"POST",

        headers:{

            "Content-Type":"application/json",
            "X-CSRFToken":
            "{{csrf_token}}"

        },

        body:JSON.stringify({

            letra:letra

        })

    })

    .then(r=>r.json())

    .then(data=>{

        alert(
        "Cambios guardados"
        );

    });

}

function exportarPDF(id){

    window.location=
    "/exportar-pdf/"+id+"/";

}

function agregarServicio(id){

    alert(
    "Lo conectaremos luego"
    );

}



/* =========================================================
   CATEGORIAS - IMAGEN POR TARJETA EN RESPONSIVE
   ========================================================= */
(function () {
    function configurarCategoriasResponsive() {
        var layout = document.querySelector('.interactive-process-layout');
        if (!layout) return;

        var mobile = window.innerWidth <= 991;
        var items = layout.querySelectorAll('.interactive-process-item');
        var images = layout.querySelectorAll('.interactive-process-image');

        var style = document.getElementById('categorias-responsive-style');
        if (!style) {
            style = document.createElement('style');
            style.id = 'categorias-responsive-style';
            style.textContent = `
                @media (max-width: 991px) {
                    .interactive-process-layout {
                        min-height: auto !important;
                    }
                    .interactive-process-layout .interactive-con-inner {
                        min-height: auto !important;
                    }
                    .interactive-process-layout .interactive-process-list-image {
                        display: none !important;
                    }
                    .interactive-process-layout .interactive-process-item {
                        position: relative !important;
                        width: 50% !important;
                        min-height: 360px;
                        background-color: #010101 !important;
                        background-repeat: no-repeat !important;
                        background-position: center center !important;
                        background-size: cover !important;
                        overflow: hidden;
                    }
                    .interactive-process-layout .interactive-process-item::before {
                        content: '';
                        position: absolute;
                        inset: 0;
                        background: rgba(0,0,0,.48);
                        z-index: 1;
                    }
                    .interactive-process-layout .interactive-process-item > * {
                        position: relative;
                        z-index: 2;
                    }
                    .interactive-process-layout .interactive-process-item:not(.mobile-image-active) {
                        background-image: none !important;
                    }
                }
                @media (max-width: 575px) {
                    .interactive-process-layout .interactive-process-item {
                        width: 50% !important;
                        min-height: 330px;
                    }
                }
            `;
            document.head.appendChild(style);
        }

        if (!mobile) {
            items.forEach(function (item) {
                item.style.backgroundImage = '';
                item.classList.remove('mobile-image-active');
            });
            return;
        }

        items.forEach(function (item, index) {
            var image = layout.querySelector('.interactive-process-image.img-' + index);
            var bg = image ? image.style.backgroundImage : '';
            if (!bg && image) bg = window.getComputedStyle(image).backgroundImage;
            item.dataset.mobileBg = bg || '';

            if (item.classList.contains('activate')) {
                item.classList.add('mobile-image-active');
                item.style.backgroundImage = item.dataset.mobileBg;
            } else {
                item.classList.remove('mobile-image-active');
                item.style.backgroundImage = 'none';
            }
        });

        items.forEach(function (item) {
            item.onclick = function () {
                items.forEach(function (other) {
                    other.classList.remove('activate', 'mobile-image-active');
                    other.style.backgroundImage = 'none';
                });

                item.classList.add('activate', 'mobile-image-active');
                item.style.backgroundImage = item.dataset.mobileBg || '';
            };
        });
    }

    configurarCategoriasResponsive();
    window.addEventListener('resize', configurarCategoriasResponsive);
})();
